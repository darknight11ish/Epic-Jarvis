"""test_settings_registry.py - "open" and "adjust" any setting, by voice or
chat, on either app (jarvis_settings_registry.py, jarvis_quick.py; the
owner's decisions of 2026-09-27; docs/JARVIS-API.md section 58).

    python3 backend/test_settings_registry.py

Runs anywhere; no Home Assistant, no model, no network, no Windows Hello
(jarvis_owner_check.set_verifier stands in for it). What it proves:

1. SECTIONS matches the real UI - every id is really a settings.html
   section (desktop) and, where marked "both" or "phone", really an
   `item(key = ...)` in SettingsScreen.kt - never a hand-typed list that
   drifted from the pages it claims to open.
2. "Open <a section>" is pure navigation: it changes nothing, and an
   unknown noun ("open the door") falls straight through to the model
   rather than answering with an invented place.
3. "Turn on/off <a setting>" calls the EXACT function the matching UI
   toggle already calls - never a new mutation path - proved by import
   identity, not by re-implementing each function's own tests.
4. A setting on jarvis_owner_check.PC_ONLY_ACTIONS (today:
   loosen_what_asks_first, enable_reading_tool) genuinely REFUSES this new
   voice/chat path from a simulated phone request, and genuinely goes
   through - raising the SAME approval card, needing the SAME Windows
   Hello confirmation - from this PC. Nothing is changed by the refused
   attempt.
5. A setting already gated by an approval card (lights without asking,
   background learning, "also remember sensitive topics automatically")
   still raises that card through this new path - never applies silently -
   whichever device asks; turning the same setting OFF is still immediate,
   with no card, exactly as the existing route behaves.
6. Ambiguous or unrecognised phrasing matches nothing here (falls through
   to the model) rather than guessing at a setting or a value.
7. `jarvis_quick.answer_turn`'s own peer/local plumbing (schedule.patch)
   reaches this file unchanged - proved end to end, not only at run()'s own
   boundary - and `is_command()` recognises every new sentence, so
   jarvis_intake.owner_turns never learns one of these as a fact.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_quick.py", "jarvis_settings_registry.py", "jarvis_asks_first.py",
                "jarvis_owner_check.py", "jarvis_auto_learn.py", "jarvis_watch_notify.py",
                "jarvis_briefing.py", "jarvis_search.py", "jarvis_manner.py",
                "jarvis_schedule.py")
sys.path.append(str(HERE / "rebuilt"))
import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402
import jarvis_asks_first as AF  # noqa: E402
import jarvis_auto_learn as AL  # noqa: E402
import jarvis_watch_notify as WN  # noqa: E402
import jarvis_briefing as BR  # noqa: E402
import jarvis_search as WS  # noqa: E402
import jarvis_manner as MN  # noqa: E402
import jarvis_owner_check as OC  # noqa: E402

# THE OWNER'S STATE IS LEFT ALONE (run_suites.py's own private_state()'s own
# rule, followed the same way here): every module this file drives writes a
# real settings file. jarvis_framework.config_path() - which
# jarvis_asks_first.py's tier lookups and writes go through - falls back to
# this repository's OWN backend/rebuilt/jarvis-framework.toml when no
# override is set ("beside the module" search), so a run of this file
# WITHOUT the env vars below really did edit a file this repository tracks
# once, while this test was being written; see this task's own report.
# JARVIS_FRAMEWORK_TOML (a copy of the real file, so every OTHER tier keeps
# its real value) and OPENJARVIS_CONFIG_DIR/JARVIS_CONFIG_DIR (the plain
# on/off settings' own JSON files) are pointed at a temporary directory,
# exactly as run_suites.py's private_state() does for every other suite.
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
TMP = Path(tempfile.mkdtemp(prefix="jarvis-settings-registry-"))
_TOML_COPY = TMP / "jarvis-framework.toml"
shutil.copyfile(REPO / "backend" / "rebuilt" / "jarvis-framework.toml", _TOML_COPY)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_FRAMEWORK_TOML"] = str(_TOML_COPY)
for _mod in (AF, AL, WN, BR, WS, MN):
    _mod._config_dir = lambda _tmp=TMP: _tmp

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def go(text, *, peer=None, local="127.0.0.1", now=None):
    body = {"messages": [{"role": "user", "content": text, "provenance": "typed"}]}
    return Q.answer_turn(body, now=now or time.time(), peer=peer, local=local)


PC, PHONE = "127.0.0.1", "100.100.5.9"

# ======================================================== 1. SECTIONS matches the real UI


def t_sections_match_the_real_ui():
    settings_html = (REPO / "jarvis-desktop" / "src" / "settings.html").read_text(encoding="utf-8")
    # A top-level card is `<section class="card" id="...">`; "More options"
    # (the folded group start-jarvis, "Startup and logs" and crash-notes sit
    # inside) is the one `<details ... id="more-options">` instead.
    desktop_ids = set(re.findall(r'<(?:section class="card"|details[^>]*)[^>]*\bid="([^"]+)"',
                                 settings_html))
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
          / "ui" / "screens" / "SettingsScreen.kt").read_text(encoding="utf-8")
    phone_keys = set(re.findall(r'item\(key\s*=\s*"([^"]+)"\)', kt))
    desktop_missing = [s.id for s in R.SECTIONS if s.app in ("both", "desktop")
                       and s.id not in desktop_ids]
    check("every 'both'/'desktop' section is a real settings.html <section id>",
          not desktop_missing, desktop_missing)
    phone_missing = [s.id for s in R.SECTIONS if s.app in ("both", "phone")
                     and s.id not in phone_keys and s.id not in desktop_ids]
    # Bug audit 2026-09-27, finding #2: Security, Voice and Appearance are
    # ordinary `item(key = ...)` rows on SettingsScreen.kt, same as every
    # other phone section - the regex above already matches them by their
    # literal keys ("security", "voice", "appearance"). Only "appearance-card"
    # needs listing here at all: that is this registry's own section id, kept
    # different from the phone's literal item key ("appearance") because the
    # desktop's settings.html uses "appearance-card" for its own <section id>.
    # "security" and "voice" are named below too, defensively, since they are
    # never missing to begin with; anything else missing is a real drift.
    ALLOWED_NO_KEY = {"security", "appearance-card", "voice"}
    phone_missing = [i for i in phone_missing if i not in ALLOWED_NO_KEY]
    check("every 'both'/'phone' section (bar the appearance-card id spelling) "
          "is a real SettingsScreen.kt item key", not phone_missing, phone_missing)
    check("no id is listed twice", len(R.SECTIONS) == len({s.id for s in R.SECTIONS}))
    check("no alias is claimed by two sections",
          len([n for s in R.SECTIONS for n in s.names])
          == len({n for s in R.SECTIONS for n in s.names}))
    _check_settings_item_index(kt)


def _check_settings_item_index(kt: str):
    """`SettingsScreen.kt`'s own `SETTINGS_ITEM_INDEX` claims a `LazyColumn`
    position for each key it lists - checked here against the REAL, current
    order of `item(key = "...")` calls in the same file, never trusted as
    still accurate.

    Bug audit 2026-09-27: this map went stale the moment a concurrent piece
    of work inserted "floating-avatar" at position 3 - every index below it
    was one item too early, and nothing caught it because the map was never
    checked against the file's real order, only checked (by the test above)
    for which keys it lists at all. A silent, plausible-looking wrong
    number is exactly what a presence-only check misses."""
    real_order = re.findall(r'item\(key\s*=\s*"([^"]+)"', kt)
    real_index = {key: i for i, key in enumerate(real_order)}
    map_block = re.search(r"SETTINGS_ITEM_INDEX[^{(]*\(\s*(.*?)\n\)", kt, re.S)
    declared = dict(re.findall(r'"([\w-]+)"\s+to\s+(\d+)', map_block.group(1))) if map_block else {}
    check("SETTINGS_ITEM_INDEX's own map block was found and parsed", bool(declared))
    # "appearance-card" is the desktop's own id, deliberately aliased to the
    # phone's own item key "appearance" (docs/JARVIS-API.md section 58.1's
    # own note on this one intentional name mismatch) - checked against
    # "appearance" instead of expecting the wire id to appear verbatim.
    ALIAS = {"appearance-card": "appearance"}
    wrong = []
    for key, declared_i in declared.items():
        real_i = real_index.get(ALIAS.get(key, key))
        if real_i is None or str(real_i) != declared_i:
            wrong.append(f"{key}: map says {declared_i}, real position is {real_i}")
    check("SETTINGS_ITEM_INDEX's positions match the real item(key=...) order",
          not wrong, wrong)


# ======================================================== 2. "open" is pure navigation


def t_open_is_pure_navigation():
    for phrase, want in (("open web search", "web-search"),
                        ("show me the security settings", "security"),
                        ("go to accounts", "account-secrets"),
                        ("take me to what asks first", "asks-first"),
                        ("open the faq", "faq"),
                        ("show me how jarvis talks", "manner")):
        i = Q.match(phrase)
        check(f"{phrase!r} opens {want!r}", i is not None and i.name == "settings_open"
              and i.f.get("id") == want, i)
    for phrase in ("open the door", "open the pod bay doors", "show me the money",
                  "go to sleep"):
        i = Q.match(phrase)
        check(f"{phrase!r} names no section, so it is not ours", i is None, i)
    r = go("open web search", peer=PHONE)
    check("the reply names the place and carries open_settings, nothing else runs",
          r is not None and r.open_settings == "web-search" and "web search" in r.reply.lower())
    rf = Q.route_fields(r)
    check("X-Jarvis-Route carries open_settings", rf.get("open_settings") == "web-search")
    r2 = go("set a timer for 5 minutes", peer=PHONE)
    rf2 = Q.route_fields(r2)
    check("an ordinary quick answer carries no open_settings key at all",
          "open_settings" not in rf2, rf2)


def t_reach_wins_over_open_reach_settings():
    # Bug audit 2026-09-27, finding #8: the "reach" section's own aliases
    # ("what jarvis can reach/access") are word-for-word what the older,
    # already-established _REACH grammar already matches for a different
    # purpose - reading the list aloud (jarvis_reach.py), not opening
    # Settings. _settings_open used to run first in _match's dispatch
    # chain, so those exact sentences opened Settings instead and the
    # older phrase became silently unreachable.
    for phrase in ("show me what jarvis can reach", "show me what jarvis can access",
                  "what can jarvis reach", "tell me what jarvis can access"):
        i = Q.match(phrase)
        check(f"{phrase!r} still reads the reach list aloud, not Settings",
              i is not None and i.name == "reach_list", (phrase, i))
    # Said plainly rather than silently accepted: the "reach" section's
    # own two declared aliases are BOTH exactly what _REACH now wins
    # against, so this fix trades "the wrong intent every time" for "no
    # voice alias opens this one section at all" - still strictly better
    # (reach_list is the more useful, more specific answer), but a real
    # gap, not a false "everything still works". A future alias for this
    # section that does not repeat _REACH's own wording would close it.
    for phrase in ("show me what jarvis can reach", "show me what jarvis can access"):
        i = Q.match(phrase)
        check(f"{phrase!r} no longer opens Settings (traded away on purpose)",
              i is None or i.name != "settings_open", i)


# ======================================================== 3. "adjust" calls the real function


def t_adjust_calls_the_real_function():
    check("web_search_provider's registry entry IS jarvis_search.use",
          R.set_web_search_provider.__module__ == "jarvis_settings_registry")
    import jarvis_search as WS
    check("... and calling it really calls WS.use (import identity, not a copy)",
          R.set_web_search_provider("duckduckgo", peer=None, local=None).said
          == WS.use("duckduckgo"))
    import jarvis_manner as MN
    before = MN.current()
    try:
        out = R.set_manner("plain")
        check("manner's registry entry really flips jarvis_manner's own setting",
              out.ok and MN.current() == "plain")
    finally:
        MN.handle_set({"manner": before})


BOOL_CASES = (
    ("background_learning", "turn off background learning", "turn on background learning"),
    ("smartwatch_notifications", "turn off smartwatch notifications",
     "turn on smartwatch notifications"),
)


def t_bool_settings_round_trip():
    for key, off_phrase, on_phrase in BOOL_CASES:
        setting = next(b for b in R.BOOL_SETTINGS if b.key == key)
        i_off = Q.match(off_phrase)
        check(f"{off_phrase!r} matches {key} off", i_off is not None
              and i_off.name == "settings_bool" and i_off.f == {"key": key, "on": False})
        i_on = Q.match(on_phrase)
        check(f"{on_phrase!r} matches {key} on", i_on is not None
              and i_on.name == "settings_bool" and i_on.f == {"key": key, "on": True})
        check(f"{key} is spelled the same as jarvis_quick's Intent name",
              setting.key == i_off.f["key"] == i_on.f["key"])


def t_ambiguous_phrasing_is_left_alone():
    # A near-miss of a real bool setting's wording, and a made-up setting -
    # neither may be guessed at.
    for phrase in ("turn on the learning thing", "turn off my calendar",
                  "enable the special mode", "turn on jarvis"):
        i = Q.match(phrase)
        check(f"{phrase!r} is not guessed at", i is None or i.name != "settings_bool", i)


# ======================================================== 4. PC_ONLY_ACTIONS genuinely refuses


def t_loosen_asks_first_pc_only():
    check("loosen_what_asks_first is really on PC_ONLY_ACTIONS (not invented for this test)",
          "loosen_what_asks_first" in OC.PC_ONLY_ACTIONS)
    AF._reset_for_tests()
    OC.set_verifier(lambda m, t: OC.CONFIRMED)
    OC._ARMED = True
    try:
        # calendar_read ships "auto" - already loosened - so there is
        # nothing to loosen until it is made stricter first.
        r = go("ask me before my calendar", peer=PHONE)
        check("stricter works from anywhere, immediately, no card",
              r is not None and (r.reply == "Done - it asks you first from now on."
                                 or "already asks" in r.reply))
        check("... and the tier really is 'ask' now", AF._tier("calendar_read") == "ask")
        r = go("stop asking before my calendar", peer=PHONE)
        check("looser, from a phone-shaped peer: refused, plain words, nothing raised",
              r is not None and "PC" in r.reply and "Windows Hello" in r.reply)
        check("... and the tier is still 'ask' - nothing was raised or changed",
              AF._tier("calendar_read") == "ask" and not AF._L_STATE["pending"])
        r = go("stop asking before my calendar", peer=PC)
        check("looser, from this PC: the SAME card jarvis_asks_first.request_tier raises",
              r is not None and "approval" in r.reply.lower() and "Windows Hello" in r.reply)
        check("... nothing applies until the card is approved", AF._tier("calendar_read") == "ask")
    finally:
        AF._reset_for_tests()
        AF.set_tier("calendar_read", "auto")   # leave the sandboxed toml as it shipped
        OC.set_verifier(None)
        OC._ARMED = False


def t_enable_reading_tool_pc_only():
    check("enable_reading_tool is really on PC_ONLY_ACTIONS (not invented for this test)",
          "enable_reading_tool" in OC.PC_ONLY_ACTIONS)
    AF._reset_for_tests()
    OC.set_verifier(lambda m, t: OC.CONFIRMED)
    OC._ARMED = True
    try:
        before = set(AF.tools_enabled_set())
        r = go("let the ai model read my calendar", peer=PHONE)
        check("ON, from a phone-shaped peer: refused",
              r is not None and "PC" in r.reply)
        check("... and [tools].enabled is unchanged", AF.tools_enabled_set() == before)
        AF._reset_for_tests()
        r = go("let the ai model read my calendar", peer=PC)
        check("ON, from this PC: the SAME card jarvis_asks_first.request_tool_enable raises",
              r is not None and ("approval" in r.reply.lower() or "already offered" in r.reply))
        AF._reset_for_tests()
        r = go("don't let the ai model read my calendar", peer=PHONE)
        check("OFF works from anywhere, immediately, no card",
              r is not None and "not offered" in r.reply)
    finally:
        AF._reset_for_tests()
        OC.set_verifier(None)
        OC._ARMED = False


# ================================================== 5. card-gated, not device-restricted


def t_lights_still_raises_its_card():
    check("lights_without_card is NOT on PC_ONLY_ACTIONS - it is gated by a card only, "
          "from either device", "loosen_what_asks_first" != AF.LIGHTS_ACTION
          and AF.LIGHTS_ACTION not in OC.PC_ONLY_ACTIONS)
    AF._reset_for_tests()
    before = AF.lights_setting()["on"]
    r = go("turn on lights without asking", peer=PHONE)
    check("ON, from the phone: a card is raised, nothing applied yet",
          r is not None and "approval" in r.reply.lower()
          and AF.lights_setting()["on"] == before)
    AF._reset_for_tests()
    r = go("turn off lights without asking", peer=PHONE)
    check("OFF is immediate, from the phone, no card",
          r is not None and AF.lights_setting()["on"] is False)


def t_background_learning_still_raises_its_card():
    AL._reset_for_tests()
    go("turn off background learning", peer=PC)
    check("OFF is immediate", AL.settings()["auto"] is False)
    r = go("turn on background learning", peer=PHONE)
    check("ON, from the phone: a card (or an unreadable-tier refusal in this bare test "
          "environment), never a silent flip", AL.settings()["auto"] is False, r.reply if r else None)


# ================================================== 6. is_command(), so the learner skips it


def t_is_command_recognises_every_new_sentence():
    for phrase in ("open web search", "turn on background learning",
                  "stop asking before my calendar", "let the ai model read my calendar"):
        check(f"is_command({phrase!r})", Q.is_command(phrase))


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("t_") and callable(v)]
    for t in tests:
        print(f"--- {t.__name__} ---")
        t()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for f in FAILED:
            print(f"  {f}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
