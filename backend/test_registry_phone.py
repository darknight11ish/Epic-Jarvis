"""Does the reverse parity check catch a registry that under-reports the phone?

    python3 backend/test_registry_phone.py

WHY THIS EXISTS. The parity audit of 2026-10-10 found the registries telling
one story and the phones telling another: eight menu ids marked desktop-only
that the phone really drew, six wrong `features.json` rows, and a Settings card
(`notifications`) that no registry read at all, which is how six real desktop
controls came to be missing from the phone with CI still green.

Both checks that existed point the same way - a menu MISSING from the phone
(`MenuVisibilityTest`, `menu-visibility.mjs`) or a menu nobody listed
(`tools/check_feature_list.py`). `tools/check_registry_phone.py` is the other
direction, and this suite is what keeps IT honest:

  * the real registries pass it (the CONTROL - so a failure below is the
    made-up input and not a check that is always red);
  * a desktop-only id with no recorded reason FAILS, naming the id;
  * a "the phone has it" correction whose phone file has moved FAILS, naming
    the file and the thing it looked for;
  * a phone screen that READS an id the registry calls desktop-only FAILS,
    quoting the file and line - this is the exact shape of all eight of the
    audit's findings;
  * a section `jarvis_settings_registry.py` calls desktop-only with no
    matching desktop-only menu FAILS - the shape that let `notifications`
    rot;
  * and a parse that finds nothing RAISES rather than passing quietly, because
    a check that cannot see its input is worse than no check.

Everything is in-process: no file is written, no network, no Android build, no
model, and no state outside this run - so it is cheap enough for CI and safe to
run on the owner's PC. `backend/run_suites.py` picks it up like every other
`test_*.py`.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "backend"))
import check_registry_phone as C  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class patched:
    """Temporarily replace a module-level function, then put it back.

    The checks all read through module-level functions on purpose, so a test
    can feed them made-up input without touching a single file in the repo.
    """

    def __init__(self, **fns):
        self.fns = fns
        self.saved = {}

    def __enter__(self):
        for name, fn in self.fns.items():
            self.saved[name] = getattr(C, name)
            setattr(C, name, fn)
        return self

    def __exit__(self, *exc):
        for name, fn in self.saved.items():
            setattr(C, name, fn)
        return False


def errors() -> list:
    """Just the message text, for the assertions below."""
    return [line for _, line in C.problems()]


def t_the_real_registries_pass_and_are_read_at_all():
    """CONTROL, and the floors. A check that cannot see its input must fail."""
    bad = C.problems()
    check("CONTROL: the real registries pass the reverse check", not bad,
          "\n        ".join(line for _, line in bad))
    names = C.desktop_only_ids()
    check("the menu registry was really read", len(names) >= C.MIN_DESKTOP_ONLY, len(names))
    check("the phone's sources were really read", len(C.phone_files()) >= C.MIN_PHONE_FILES,
          len(C.phone_files()))
    check("the phone's own menu reads were really found",
          len(C.phone_menu_reads()) >= 40, len(C.phone_menu_reads()))
    check("every menu the audit corrected is recorded as one the phone has",
          len(C.PHONE_HAS) == 8, sorted(C.PHONE_HAS))
    check("the phone's own PC_ONLY list was really read",
          "notifications" in C.open_place_pc_only(), sorted(C.open_place_pc_only()))


def t_a_parse_that_finds_nothing_raises():
    """Silence is the failure this whole class of bug is made of.

    Each check reads its input through one module-level name, so feeding that
    name an empty world is enough to prove the floor really raises - and that
    is the whole point: a check that cannot see its input must not pass
    quietly.
    """
    import shutil
    import tempfile

    def raises(what) -> bool:
        try:
            what()
        except AssertionError:
            return True
        except Exception as exc:  # a wrong exception is still a bug
            print(f"        raised {type(exc).__name__}: {exc}")
            return False
        return False

    empty = Path(tempfile.mkdtemp(prefix="jarvis-empty-"))
    try:
        check("a parse that found no phone sources raises",
              _with({"PHONE_MAIN": empty}, lambda: raises(C.phone_files)))
        check("a parse that found too few phone files raises",
              _with({"MIN_PHONE_FILES": 10_000}, lambda: raises(C.phone_files)))
        check("a parse that found no phone menu reads raises",
              _with({"phone_files": lambda: []}, lambda: raises(C.phone_menu_reads)))
        check("a parse that found no Settings cards raises",
              _with({"read": lambda path: "<html></html>"},
                    lambda: raises(C.desktop_settings_card_ids)))
        check("a parse that found no menus at all raises", _menus_floor())
    finally:
        shutil.rmtree(empty, ignore_errors=True)


def _with(fns: dict, call):
    with patched(**fns):
        return call()


def _menus_floor() -> bool:
    """`desktop_only_ids` must raise on a menu list that is too short."""
    import jarvis_menus as M

    saved = M.MENUS
    try:
        M.MENUS = ()
        try:
            C.desktop_only_ids()
        except AssertionError:
            return True
        return False
    finally:
        M.MENUS = saved


def t_a_desktop_only_id_with_no_reason_fails_by_name():
    made_up = "settings.a_menu_nobody_explained"
    with patched(desktop_only_ids=lambda: [made_up]):
        got = errors()
    check("a desktop-only id with no PHONE_LACKS reason is reported, by name",
          any(made_up in line and "PHONE_LACKS" in line for line in got), got)

    # ...and the other way: a reason left behind for an id that is not
    # desktop-only any more.
    with patched(desktop_only_ids=lambda: []):
        got = errors()
    check("a PHONE_LACKS line for an id that is no longer desktop-only is reported",
          any("not a desktop-only menu any more" in line for line in got), got)


def t_a_phone_has_it_correction_that_has_gone_stale_fails():
    """The eight corrections are claims; a claim nobody re-checks is a comment."""
    with patched(PHONE_HAS={"settings.about": ("jarvis-client/does/not/exist.kt", "x")}):
        got = errors()
    check("a PHONE_HAS correction pointing at a missing file is reported",
          any("settings.about" in line and "which is not there" in line for line in got), got)

    # The file is there, the thing in it is not.
    with patched(PHONE_HAS={"settings.about": (
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/FaqScreen.kt",
            "private fun SomethingThatWasRenamed()")}):
        got = errors()
    check("a PHONE_HAS correction whose phone code moved or went is reported",
          any("SomethingThatWasRenamed" in line for line in got), got)
    # And the finding itself: still marked desktop-only while the phone has it.
    with patched(PHONE_HAS={"brain.work.undo": (
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/InboxScreen.kt",
            '"UNDO SHELF"')},
            desktop_only_ids=lambda: ["brain.work.undo"]):
        got = errors()
    check("an id the phone has and the registry still calls desktop-only is reported",
          any("under-report the phone again" in line for line in got), got)


def t_a_phone_screen_reading_a_desktop_only_id_fails_with_the_line():
    """The exact shape of all eight of the audit's findings."""
    with patched(desktop_only_ids=lambda: ["settings.notifications"],
                 phone_menu_reads=lambda: {
                     "settings.notifications": "jarvis-client/.../SettingsScreen.kt:99"}):
        got = errors()
    check("a phone screen reading a desktop-only id is reported, with the file and line",
          any("settings.notifications" in line and "SettingsScreen.kt:99" in line
              and "correct `apps`" in line for line in got), got)


def t_the_two_registries_are_held_to_each_other():
    """The `notifications` shape: a section only one registry knows about.

    `PHONE_LACKS` is emptied alongside, because the point of this test is the
    agreement check alone - a desktop-only menu left without a reason would
    otherwise fire first and mask it.
    """
    with patched(PHONE_LACKS={},
                 settings_desktop_sections=lambda: ["notifications"],
                 desktop_settings_card_ids=lambda: {"notifications", "voice"},
                 # Every other desktop-only section is named, so the ONE thing
                 # this test is about is the one thing it reports.
                 open_place_pc_only=lambda: set(C.SETTINGS_DESKTOP_ONLY),
                 desktop_only_ids=lambda: []):
        got = errors()
    check("a desktop Settings card called desktop-only with no such menu is reported",
          any("no desktop-only `settings.notifications` menu" in line for line in got), got)

    # ...and the same disagreement for a section that is NOT a real card at all
    # (a row inside one): the first loop's own words.
    with patched(PHONE_LACKS={},
                 settings_desktop_sections=lambda: ["a-section-nobody-listed"],
                 desktop_settings_card_ids=lambda: {"notifications", "voice"},
                 open_place_pc_only=lambda: set(C.SETTINGS_DESKTOP_ONLY),
                 desktop_only_ids=lambda: []):
        got = errors()
    check("a registry section that is no menu and no card is reported",
          any("the two registries disagree" in line for line in got), got)

    # ...and the phone's own "only on your PC" answer is held to it, because
    # that list is what the owner actually hears.
    with patched(PHONE_LACKS={},
                 settings_desktop_sections=lambda: [],
                 desktop_settings_card_ids=lambda: {"notifications"},
                 open_place_pc_only=lambda: set(),
                 desktop_only_ids=lambda: ["settings.notifications"]):
        got = errors()
    check("a desktop-only section the phone does not list as PC-only is reported",
          any("PC_ONLY does not name" in line for line in got), got)


if __name__ == "__main__":
    for fn in (t_the_real_registries_pass_and_are_read_at_all,
               t_a_parse_that_finds_nothing_raises,
               t_a_desktop_only_id_with_no_reason_fails_by_name,
               t_a_phone_has_it_correction_that_has_gone_stale_fails,
               t_a_phone_screen_reading_a_desktop_only_id_fails_with_the_line,
               t_the_two_registries_are_held_to_each_other):
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
