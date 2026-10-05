"""Home's navigation row is shown by default (ease-of-use audit, 2026-09-27,
do-first table row 3: "Phone: show the way around").

    py -3 backend/test_home_nav_row.py

WHAT THIS IS ABOUT

Home's row of tabs - Brain, Inbox, Live, Appearance, Help - was hidden behind
a swipe and a 14x8 dp chevron (`docs/ease-audit-2026-09-27/everyday.md` §63),
so the way around the app was invisible to anyone who did not already know it
was there. `AppearanceStore.kt`'s `Look.navAlwaysShown` defaulted to `false`.
Since 2026-10-05 it defaults to `true`, and "Hidden until swiped" stays an
option in Appearance with its behaviour unchanged.

THE PART THAT COULD GO WRONG

An owner who had already chosen "Hidden until swiped" must keep it: only a
fresh install's default changes. The record's own field is what says so -
every field of `Look` is written on save, so a stored `nav_always_shown:
false` is a choice, and `tabsRowShown` (which `loadLook` calls) reads it back
as false. A plain flip of the default is safe exactly because of that, and
this suite pins both halves: the defaults, and the three-way rule.

The JVM unit test for the same two things is
`jarvis-client/app/src/test/java/com/jarvis/client/data/LookTest.kt`. There is
no Android SDK on this machine, so that one cannot be RUN here; this suite
reads the same Kotlin sources and runs anywhere, which is the repo's own
pattern for the phone (backend/test_owner_check.py, test_settings_registry.py).

    py -3 backend/test_home_nav_row.py
"""
from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

KT = REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
KT_TEST = REPO / "jarvis-client" / "app" / "src" / "test" / "java" / "com" / "jarvis" / "client"

STORE = (KT / "data" / "AppearanceStore.kt").read_text(encoding="utf-8")
HOME = (KT / "ui" / "screens" / "HomeScreen.kt").read_text(encoding="utf-8")
APPEARANCE = (KT / "ui" / "screens" / "AppearanceScreen.kt").read_text(encoding="utf-8")
LOOK_TEST = (KT_TEST / "data" / "LookTest.kt").read_text(encoding="utf-8")

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def boolean_default(src: str, decl: str):
    """The true/false after `decl` in a Kotlin declaration, or None.

    `decl` ends at the `=`, so `boolean_default(src, "val navAlwaysShown:
    Boolean =")` answers the default and nothing else.
    """
    i = src.find(decl)
    if i < 0:
        return None
    m = re.search(r"\s*(true|false)\s*,", src[i + len(decl):])
    return m.group(1) if m else None


def t_the_default_is_shown():
    """Both places that carry the default say `true`."""
    got = boolean_default(STORE, "val navAlwaysShown: Boolean =")
    check("Look.navAlwaysShown defaults to shown (true)", got == "true", f"got {got!r}")
    # The state the screen is drawn from. MainActivity fills it from the look
    # above, so this one never decides in the app - but it is the other place
    # the old default was written, and a second caller would read it.
    got_home = boolean_default(HOME, "val navAlwaysShown: Boolean =")
    check("HomeState.navAlwaysShown defaults to shown too (true)", got_home == "true",
          f"got {got_home!r}")


def t_a_stored_choice_of_hidden_survives():
    """Only an unset record takes the new default; a chosen `false` stays."""
    check("the loader has a three-way rule to test (tabsRowShown exists)",
          "fun tabsRowShown(stored: Boolean?): Boolean" in STORE)
    check("... it reads the record's own field, and null only when the record is silent",
          'if (o.has("nav_always_shown")) o.optBoolean("nav_always_shown") else null' in STORE,
          "loadLook no longer tells 'the record says false' from 'the record says nothing'")
    check("... and absent takes the default, not a constant false",
          "stored ?: Look().navAlwaysShown" in STORE)
    # The promise that makes a plain flip safe: every field is written on save,
    # so a later default cannot move a setting the owner chose.
    check("the encoder still writes the field on every save",
          'put("nav_always_shown", l.navAlwaysShown)' in STORE)
    check("... under that promise, in its own words",
          "Every field is\n     * written, so a later default change does not silently move a setting" in STORE,
          [ln for ln in STORE.splitlines() if "later default change" in ln])


def t_hide_it_is_still_an_option():
    """Appearance offers both, and picking one still just sets the field."""
    check("Appearance still offers both choices",
          "options = listOf(false, true)," in APPEARANCE,
          [ln.strip() for ln in APPEARANCE.splitlines() if "options = listOf" in ln][:4])
    check("... worded 'Always shown' / 'Hidden until swiped'",
          '"Always shown"' in APPEARANCE and '"Hidden until swiped"' in APPEARANCE)
    check("... and picking one writes the setting, unchanged",
          "onPick = { onLookChange(look.copy(navAlwaysShown = it)) }" in APPEARANCE)
    check("... in the row called \"Tabs row\"", 'Setting(title = "Tabs row")' in APPEARANCE)


def t_home_still_hides_it_when_asked():
    """The row is drawn from the setting, and the swipe still opens it."""
    check("Home shows the row when the setting says so, or when it was swiped open",
          "val navShown = state.navAlwaysShown || navOpen" in HOME)
    check("... and the swipe/tap toggle is still wired when it is hidden",
          "onNavToggle = if (state.navAlwaysShown) null else" in HOME)


def t_the_jvm_test_pins_the_same_two_things():
    """The Kotlin unit test cannot be run here (no Android SDK), so: is it there?

    A test that exists and says the wrong thing is worse than none, so this
    reads the two assertions rather than trusting the file name.
    """
    check("LookTest asserts the new default", "assertTrue(look.navAlwaysShown)" in LOOK_TEST)
    check("... and no longer asserts the old one", "assertFalse(look.navAlwaysShown)" not in LOOK_TEST)
    check("LookTest covers a stored choice of hidden",
          "tabsRowShown(false)" in LOOK_TEST and "tabsRowShown(null)" in LOOK_TEST)


def t_the_check_can_fail():
    """CONTROL ON THE CONTROL: the extractor against the source it replaced.

    A guard nobody has watched fail is a guess. This is the AppearanceStore
    text as it was before the change, with the old default and the old
    two-way loader line.
    """
    old = (STORE
           .replace("val navAlwaysShown: Boolean = true,", "val navAlwaysShown: Boolean = false,")
           .replace("fun tabsRowShown(stored: Boolean?): Boolean = stored ?: Look().navAlwaysShown",
                    "fun tabsRowShown(stored: Boolean?): Boolean = stored ?: false"))
    check("REJECTED: the old default reads as false",
          boolean_default(old, "val navAlwaysShown: Boolean =") == "false",
          "the extractor cannot tell the two defaults apart - these checks prove nothing")
    check("REJECTED: an absent record with the old rule reads as hidden",
          "stored ?: Look().navAlwaysShown" not in old)


if __name__ == "__main__":
    for fn in (t_the_default_is_shown, t_a_stored_choice_of_hidden_survives,
               t_hide_it_is_still_an_option, t_home_still_hides_it_when_asked,
               t_the_jvm_test_pins_the_same_two_things, t_the_check_can_fail):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
