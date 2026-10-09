"""Does every switch on the desktop Settings page have a row in the table?

    python3 test_settings_rows.py

WHY THIS EXISTS

`backend/jarvis_settings_registry.py`'s SETTINGS_ROWS is the one table behind
the desktop page's switch rows, the contract fixture both apps read, and the
phone's generated `SettingsCatalog.kt` (`tools/gen_settings_cases.py`). Three
other things already hold it in place:

  * `tools/gen_settings_cases.py --check` - the four generated files are what
    the table says, and every row on the page renders from it byte for byte;
  * `jarvis-desktop/tests/settings-catalogue.mjs` - the page, the fixture and
    the desktop catalogue agree, row order included;
  * `jarvis-client/.../SettingsCatalogTest.kt` - the phone's copy is the
    fixture.

All three read the SAME table, so all three agree with each other even when
the table itself is wrong. This file is the one that asks the question from
the other end: **is a switch on the page missing from the table?** Before it,
a toggle added by hand to `settings.html` - with no registry row, no fixture
entry and no catalogue entry - passed every guard in the repository, because
every guard started from the table.

WHAT IT CHECKS

  1. every `<label class="toggle">` on the page has a SETTINGS_ROWS row;
  2. ...and no SETTINGS_ROWS row names a toggle the page does not have;
  3. the page's own order IS the rows' `order` (row order was unprotected
     before this work);
  4. each row's `indent` is the page's real indentation - the number the
     generator needs to put the row back where it found it;
  5. the count is stated out loud, so a number that moves is noticed rather
     than absorbed. It is **26**, and it has been mis-reported as 19: a bare
     `<label class="toggle">` string match misses the seven rows that also
     carry a label id;
  6. every row's `setting` names a real BoolSetting, or is None. None is the
     normal case (20 of the 26): those rows have no spoken "adjust", and
     putting them in BOOL_SETTINGS would make the phrase match and the
     dispatch then fail - `jarvis_quick.py:2788` matches on that table and
     `:3703` dispatches on the same key.

WHAT IT DOES NOT CHECK

  It does not read the two apps' words: `settings-catalogue.mjs` and
  `SettingsCatalogTest.kt` do that. It does not prove the switches work - that
  needs the app running. And it does not check the eleven rows whose visible
  words the PC sends at read time: for those the table holds a FALLBACK, and
  what the owner reads is decided on the PC.

Needs nothing from the owner's PC; runs anywhere, including CI.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import jarvis_settings_registry as R  # noqa: E402

SETTINGS_HTML = REPO / "jarvis-desktop" / "src" / "settings.html"

#: The number of `<label class="toggle">` rows the page has. Stated rather
#: than computed so that a row quietly disappearing is a failure here rather
#: than a smaller number that every other check happily agrees with.
EXPECTED_ROWS = 26

#: The rows that are not settings switches, with the reason. These are in
#: SETTINGS_ROWS (so the page and the table still agree) but carry
#: `setting_row=False`.
NOT_SWITCHES = {
    "spd-accept": "the spending screen's hidden 'accept every column' control",
}

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def page_rows():
    """The page's toggle rows, in page order, as
    `(dom_id, indent, row_id)` - read the same way the generator reads them."""
    html = SETTINGS_HTML.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r'^([ \t]*)<label([^>]*\bclass="toggle[^"]*"[^>]*)>[ \t]*$',
                         html, re.M):
        indent = len(m.group(1))
        attrs = m.group(2)
        end = html.index("</label>", m.end())
        body = html[m.end():end]
        found = re.search(r'<input\b[^>]*\bid="([^"]+)"', body)
        row_id = re.search(r'\bid="([^"]+)"', attrs)
        out.append((found.group(1) if found else "", indent,
                    row_id.group(1) if row_id else ""))
    return out


def t_every_toggle_has_a_row():
    """The direction nothing else checked: the page may not grow a switch the
    table has never heard of."""
    page = page_rows()
    known = {r.dom_id for r in R.SETTINGS_ROWS}
    missing = [dom for dom, _, _ in page if dom not in known]
    check("every <label class=\"toggle\"> on the page has a SETTINGS_ROWS row",
          not missing,
          f"{missing} - add a SettingRow for each, then run "
          f"python3 tools/gen_settings_cases.py")


def t_no_row_without_a_toggle():
    """...and the table may not name a switch the page does not draw.

    The phone's two rows are the named exception: the phone has them and the
    desktop page does not, which is the whole point of `owner`."""
    page = {dom for dom, _, _ in page_rows()}
    extra = [r.dom_id for r in R.DESKTOP_ROWS if r.dom_id not in page]
    check("every desktop SETTINGS_ROWS row is a real toggle on the page",
          not extra, f"{extra} - the row was deleted from settings.html")
    phone = [r.dom_id for r in R.SETTINGS_ROWS if r.owner == "phone"]
    check("the phone's own rows are the only rows with no desktop toggle",
          sorted(phone) == ["phone-notify", "watch-notify"], phone)


def t_the_count_is_what_it_is():
    """The number, said out loud.

    It has been wrong twice: "19" (a bare-string match that misses the seven
    rows carrying a label id) and "12 PC-worded rows" (which counted
    `spd-accept`, whose span starts empty and is filled by a local constant).
    A test cannot know the right number by itself, so it pins the measured one
    and explains what to re-measure if it moves."""
    page = page_rows()
    check(f"the page has exactly {EXPECTED_ROWS} toggle rows",
          len(page) == EXPECTED_ROWS,
          f"found {len(page)} - if a switch was really added or removed, "
          f"re-count and update EXPECTED_ROWS and SETTINGS_ROWS together")
    bare = len(re.findall(r'^[ \t]*<label class="toggle">[ \t]*$',
                          SETTINGS_HTML.read_text(encoding="utf-8"), re.M))
    check("19 of them are bare `<label class=\"toggle\">`, 7 carry a label id",
          bare == 19 and len(page) - bare == 7,
          f"bare={bare}, with-id={len(page) - bare} - this is the trap that "
          f"produced the wrong '19'")
    check("all 26 desktop rows are described",
          len(R.DESKTOP_ROWS) == EXPECTED_ROWS, str(len(R.DESKTOP_ROWS)))
    check("the two phone rows are described too",
          len(R.SETTINGS_ROWS) == EXPECTED_ROWS + 2, str(len(R.SETTINGS_ROWS)))


def t_row_order_matches_the_page():
    """Row-level order was unprotected before this work: a switch that moved
    to another card, or two rows that swapped, were both silent."""
    page = [dom for dom, _, _ in page_rows()]
    want = [r.dom_id for r in sorted(R.DESKTOP_ROWS, key=lambda r: r.order)]
    check("the page's row order is the rows' own `order`", page == want,
          f"page: {page}\ntable: {want}")


def t_indent_matches_the_page():
    """The generator puts each row back at ITS depth - the rows are not all at
    one - so a recorded indent that is wrong silently re-indents the page."""
    page = {dom: indent for dom, indent, _ in page_rows()}
    wrong = [f"{r.dom_id}: table {r.indent}, page {page.get(r.dom_id)}"
             for r in R.DESKTOP_ROWS if page.get(r.dom_id) != r.indent]
    check("every row's recorded indent is the page's real indentation",
          not wrong, "; ".join(wrong))


def t_label_ids_match_the_page():
    """The seven label ids are how a module hides or relabels a whole row
    (`briefing-settings.js:115` and friends), and the six span ids are how the
    PC's own words are written in. Both are read off the page."""
    page = {dom: row_id for dom, _, row_id in page_rows()}
    wrong = [f"{r.dom_id}: table {r.row_id!r}, page {page.get(r.dom_id)!r}"
             for r in R.DESKTOP_ROWS if page.get(r.dom_id, "") != r.row_id]
    check("every row's <label> id is the page's own", not wrong, "; ".join(wrong))
    with_ids = sorted(r.dom_id for r in R.DESKTOP_ROWS if r.row_id)
    check("seven rows carry a <label> id", len(with_ids) == 7, str(with_ids))


def t_setting_links_are_real():
    """A row's `setting` must name a BoolSetting, or be None.

    None is the normal case and NOT a gap: `jarvis_quick.py:2788` matches a
    spoken phrase against `BOOL_SETTINGS`'s names and `:3703` dispatches on
    the same key, so a row added there without a working setter would match
    and then fail - a silent lie, and nothing checks that today."""
    keys = {b.key for b in R.BOOL_SETTINGS}
    bad = [f"{r.dom_id} -> {r.setting!r}" for r in R.SETTINGS_ROWS
           if r.setting and r.setting not in keys]
    check("every row's `setting` names a real BoolSetting", not bad, "; ".join(bad))
    linked = sorted(r.dom_id for r in R.DESKTOP_ROWS if r.setting)
    check("six desktop rows are the same switch as a spoken setting",
          len(linked) == 6, f"{linked} - if this grew, the row was given a setter")
    # The spoken settings with no desktop toggle. Three have no switch row at
    # all on this page (two are on the Brain's Memory tab, one is a row inside
    # "What asks first"), and two are the phone's own.
    orphans = sorted(keys - {r.setting for r in R.DESKTOP_ROWS if r.setting})
    check("...and the BoolSettings with no desktop row are the known five",
          orphans == ["background_learning", "learn_sensitive_topics",
                      "lights_without_card", "phone_notifications",
                      "smartwatch_notifications"], str(orphans))
    phone_linked = sorted(r.setting for r in R.SETTINGS_ROWS
                          if r.owner == "phone" and r.setting)
    check("the two phone rows name the two phone-only spoken settings",
          phone_linked == ["phone_notifications", "smartwatch_notifications"],
          str(phone_linked))


def t_not_switches_are_the_known_one():
    """`spd-accept` looks exactly like a settings toggle and is not one: it is
    the spending screen's hidden accept-all control, filled in at runtime."""
    not_setting = sorted(r.dom_id for r in R.SETTINGS_ROWS if not r.setting_row)
    check("exactly one row is flagged as not being a setting",
          not_setting == sorted(NOT_SWITCHES), str(not_setting))
    for dom, why in NOT_SWITCHES.items():
        row = R.setting_row(dom)
        check(f"{dom} is still the row described as {why!r}",
              row is not None and row.hidden and not row.setting_row,
              f"hidden={getattr(row, 'hidden', None)} "
              f"setting_row={getattr(row, 'setting_row', None)}")


def t_fallback_rows_are_the_known_ten():
    """Ten rows get their visible words from the PC at read time, so the words
    in the table are a FALLBACK. The list is a claim about the desktop
    JavaScript, so it is pinned here and explained."""
    want = ["sky-show", "voice-one-moment", "voice-heard-sound", "mn-humor",
            "coach-enabled", "sec-app-lock", "sec-private", "cv-face-switch",
            "ws-enabled", "ws-ask"]
    got = sorted(r.dom_id for r in R.DESKTOP_ROWS if r.fallback)
    check("ten rows are marked as PC-worded, and they are the right ten",
          got == sorted(want), f"{got}\nexpected {sorted(want)}")
    check("spd-accept is NOT one of them (its words are a local constant)",
          not R.setting_row("spd-accept").fallback)
    check("cv-better-switch is NOT one of them (nothing rewrites its detail)",
          not R.setting_row("cv-better-switch").fallback)


def t_bool_settings_did_not_grow():
    """The spoken table is not this work's business: the rows were added
    beside it, not inside it. Eleven before, eleven now."""
    check("BOOL_SETTINGS still holds its eleven spoken settings",
          len(R.BOOL_SETTINGS) == 11, str(len(R.BOOL_SETTINGS)))


def main() -> int:
    for fn in (t_every_toggle_has_a_row, t_no_row_without_a_toggle,
               t_the_count_is_what_it_is, t_row_order_matches_the_page,
               t_indent_matches_the_page, t_label_ids_match_the_page,
               t_setting_links_are_real, t_not_switches_are_the_known_one,
               t_fallback_rows_are_the_known_ten, t_bool_settings_did_not_grow):
        fn()
    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED, {len(PASSED)} passed")
        for name in FAILED:
            print(f"  - {name}")
        return 1
    print(f"all {len(PASSED)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
