#!/usr/bin/env python3
"""Writes the settings switches' contract files for both apps, and checks them.

    python3 tools/gen_settings_cases.py            # write every file
    python3 tools/gen_settings_cases.py --check    # compare only

Four outputs, all made from ONE table - nothing is written by hand:

1. jarvis-desktop/tests/fixtures/settings-cases.json
2. jarvis-client/app/src/test/resources/contract/settings-cases.json
   (byte-identical to 1) - the desktop's tests/settings-catalogue.mjs and the
   phone's SettingsCatalogTest.kt read it, so neither app can carry a
   different list of switches, ids, words or row order.

3. jarvis-client/app/src/main/java/com/jarvis/client/net/SettingsCatalog.kt -
   the phone's own copy as generated Kotlin, so 26 ids and their words are
   never typed by hand.

4. The rows in jarvis-desktop/src/settings.html between the markers
   "settings-toggles:begin" and "settings-toggles:end" - the 26 switch rows
   themselves, rendered from that same table, so the page and the table
   cannot drift.

WHERE THE ONE TABLE IS. backend/jarvis_settings_registry.py's SETTINGS_ROWS,
which is also where the spoken setting names live (BOOL_SETTINGS). A row
carries its `<input>` id, its label/detail span ids, its words, its position
on the page, the card it sits in and which app owns its words; `setting`
links a row to its BoolSetting when one exists (6 of the 26 do - the other
20 have no spoken "adjust" and must not be added to BOOL_SETTINGS, see that
file's note).

WHY THE PAGE IS SPLICED RATHER THAN RENDERED AT START-UP: 19 desktop test
files read src/settings.html as TEXT and assert its ids and wording, and
voice-panel.js:1784 calls addEventListener unguarded on a row it expects to
be there - a row built at runtime would throw inside startVoicePanel and
abort that initialiser. The splice writes the same bytes the page already
has, so nothing about the running app changes.

THE WORDS ARE A FALLBACK ON TEN ROWS. Where the PC sends a row's visible
words at read time (SETTINGS_ROWS' `fallback=True`), the fixture marks them
`"fallback": true` and settings-catalogue.mjs requires the page to keep
showing exactly those words, rather than treating this table as a second
owner of what the owner reads.

ADDING OR CHANGING A ROW. Add the row to SETTINGS_ROWS
(`backend/jarvis_settings_registry.py`) with its ids, words, order, indent,
card and owner, then run this file. It will not write a page that disagrees
with the table: `write_page` re-renders every existing row from the table and
stops, printing both versions, at the first one that differs - so a new row's
markup has to be right before anything is written, and the edit that adds it
to `settings.html` is the one that proves it. `backend/test_settings_rows.py`
is what catches the other direction (a toggle on the page with no row).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import jarvis_settings_registry as R  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "settings-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "settings-cases.json")
COPIES = (DESKTOP, PHONE)
KOTLIN = (ROOT / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
          / "client" / "net" / "SettingsCatalog.kt")
JS_CATALOG = ROOT / "jarvis-desktop" / "src" / "settings-catalog.js"
HTML = ROOT / "jarvis-desktop" / "src" / "settings.html"
BEGIN = "<!-- settings-toggles:begin (tools/gen_settings_cases.py writes these; do not edit) -->"
END = "<!-- settings-toggles:end -->"
SCHEMA = 1


# --------------------------------------------------------------------------
#   The rows -> the page's own markup
# --------------------------------------------------------------------------

def _attrs(row) -> str:
    a = ' type="checkbox"'
    if row.checked:
        a += " checked"
    if row.data_live:
        a += ' data-live="true"'
    return a


def _input_tag(row) -> str:
    """The `<input ... />` tag. Recorded verbatim when the table has it (one
    row needs the other word order), built from the flags otherwise."""
    return row.input_open or f'<input id="{row.dom_id}"{_attrs(row)} />'


def _wrapped(open_line: str, text: str, close_indent: str, body_indent: str) -> list:
    """`<tag>text</tag>`, exactly as settings.html spells it.

    A one-line text keeps its closing tag on the same line. A multi-line text
    puts the words one level in from the tag that opened them and the closing
    tag back at the tag's own level - and the text's own last character is a
    newline, which IS the line break before the closing tag, so no second one
    is added."""
    if not text:
        return [open_line + "</span>"]
    if "\n" not in text:
        return [open_line + text + "</span>"]
    body = [body_indent + ln for ln in text.split("\n")]
    if text.endswith("\n"):
        body = body[:-1]              # the newline already ends the last line
    return [open_line] + body + [close_indent + "</span>"]


def markup(row, indent: int = 8) -> str:
    """One toggle row, exactly as settings.html spells it.

    Every row is `<label class="toggle">` / `<input>` / one `<span>` holding
    the words / `</label>`, and the page indents it at four depths: the label
    at `indent`, the input and that span at `indent + 2`, and the words at
    `indent + 4`. `indent` is 8, 10 or 12 depending on how deep in the cards
    the row sits, so it is passed in rather than assumed.

    Three shapes, all of them used by the page:

    1. the span holds the words directly - sharing its line for a one-line
       label (`supervise`, `autostart`), or on their own lines for a
       multi-line one (`follow-system`);
    2. the span holds a CHILD span with an id, which holds the words - the
       child shares the span's line when a detail span follows it
       (`sky-show`), or opens the next line when it is the row's last child
       (`sp-switch`, `be-switch`);
    3. the span IS the label's span, id and all, with no child
       (`spd-accept`) - and then there is no separate wrapping span at all.

    The closing `</span>` for the wrapping span is written once, at the end,
    for shapes 1 and 2 only."""
    pad, inner, deep = " " * indent, " " * (indent + 2), " " * (indent + 4)
    deeper = " " * (indent + 6)
    lab = f' id="{row.row_id}"' if row.row_id else ""
    hid = " hidden" if row.hidden else ""
    child = f'<span id="{row.label_span_id}">' if row.label_span_id else ""
    out = [f'{pad}<label class="toggle"{lab}{hid}>',
           f'{inner}{_input_tag(row)}']

    if row.label_span_is_wrapper:
        # Shape 3: the row's only span, so it takes the wrapping span's depth.
        out.append(f'{inner}<span id="{row.label_span_id}">{row.label}</span>')
    elif child and row.has_detail:
        # Shape 2a: a child span with the words, and a detail span after it.
        # The wrapper opens at the row's own inner depth; the child (and the
        # detail span below) sit one level further in.
        out += [f'{inner}<span>', f'{deep}{child}{row.label}</span>']
    elif child:
        # Shape 2b: the child span is the row's last child, so it opens its
        # own line at the wrapper's depth and the words go inside it.
        out.append(f'{inner}<span>')
        out += _wrapped(deep + child, row.label, deep, deep)
    elif row.has_detail:
        # Shape 1b: no child span, and a detail span follows - so the words
        # get a line of their own rather than sharing the wrapper's.
        out.append(f'{inner}<span>')
        out += [deep + ln for ln in row.label.split("\n")]
    elif "\n" in row.label or row.span_on_own_line:
        # Shape 1c: no child span and no detail span, but the page still puts
        # the words on their own line - at `deep`, inside the wrapping span.
        out.append(f'{inner}<span>')
        out += [deep + ln for ln in row.label.split("\n")]
    else:
        # Shape 1a: the words sit straight in the wrapping span, which opens
        # and closes on their line - `supervise` and `autostart`.
        out.append(f'{inner}<span>{row.label}</span>')
        out.append(f'{pad}</label>')
        return "\n".join(out)

    if row.has_detail:
        # The detail span always opens its own line, one level in from the
        # wrapping span, and carries an id only where the page gave it one.
        did = f' id="{row.detail_span_id}"' if row.detail_span_id else ""
        out += _wrapped(deep + f'<span class="toggle-detail"{did}>',
                        row.detail, deep, deeper)
    if not row.label_span_is_wrapper:
        out.append(f'{inner}</span>')       # close the wrapping span
    out.append(f'{pad}</label>')
    return "\n".join(out)


def rows_block() -> str:
    """Every desktop row, each at the depth the page has it at.

    This is what a reader (or a diff) should look at to see the whole set of
    rows at once. It is NOT what gets written into the page: the rows are not
    one contiguous run there - the page has other markup between them (the
    theme radios between rows 1 and 2, "Thinking levels" between rows 7 and
    8, and so on) - so `splice` puts each row back where it belongs and this
    is never used as a replacement block."""
    return "\n".join(markup(r, r.indent)
                     for r in sorted(R.DESKTOP_ROWS, key=lambda r: r.order))


def splice(doc: str, *, indent: int) -> str:
    """The page with every row written from the table, everything else byte
    for byte untouched.

    `doc` must already carry both markers. Each row is replaced IN PLACE -
    the markup between two rows is never part of the replacement - because
    the page has other elements between its toggle rows, and treating the
    rows as one run would silently delete everything in between. `indent` is
    the first row's own depth, where the BEGIN marker goes."""
    if BEGIN not in doc or END not in doc:
        raise SystemExit(f"{_name(HTML)} has no {BEGIN!r} marker")
    rows = sorted(R.DESKTOP_ROWS, key=lambda r: r.order)
    spans = _row_spans(doc)
    if len(spans) != len(rows):
        raise SystemExit(f"{_name(HTML)} has {len(spans)} toggle rows but "
                         f"SETTINGS_ROWS describes {len(rows)}")
    # Replace from the LAST row backwards, so every earlier offset stays
    # valid while the text after it changes length.
    out = doc
    for row, (s, e) in reversed(list(zip(rows, spans))):
        out = out[:s] + markup(row, row.indent) + "\n" + out[e:]
    # The markers themselves, around the block rather than around any one row.
    a = out.index(BEGIN)
    b = out.index(END, a + len(BEGIN)) + len(END)
    return out


# --------------------------------------------------------------------------
#   The four outputs
# --------------------------------------------------------------------------

def build() -> dict:
    rows = []
    for r in R.SETTINGS_ROWS:
        rows.append({
            "id": r.dom_id,
            "setting": r.setting or None,
            "owner": r.owner,
            "section": r.section,
            "order": r.order,
            "indent": r.indent,
            "input": r.dom_id,
            # The tag verbatim when the page spells it unusually (one row has
            # the type before the id); null when the ordinary order applies.
            "input_open": r.input_open or None,
            "row_id": r.row_id or None,
            "label_span": r.label_span_id or None,
            # null when the row has NO detail span; "" when it has one that
            # carries no id of its own (`face-auto`, `cv-better-switch`). The
            # difference matters: the span still has to be written.
            "detail_span": (r.detail_span_id or "") if r.has_detail else None,
            "label": r.label,
            "detail": r.detail,
            "fallback": r.fallback,
            "checked": r.checked,
            "hidden": r.hidden,
            "data_live": r.data_live,
            "setting_row": r.setting_row,
            "phone_key": r.phone_key or None,
            "source": r.source or None,
        })
    desktop = [r for r in rows if r["owner"] == "desktop"]
    return {
        "_comment": ("Generated by tools/gen_settings_cases.py from "
                     "backend/jarvis_settings_registry.py's SETTINGS_ROWS. "
                     "Do not edit by hand."),
        "schema": SCHEMA,
        "counts": {
            "all": len(rows),
            "desktop": len(desktop),
            "phone": len(rows) - len(desktop),
            "fallback": sum(1 for r in desktop if r["fallback"]),
            # Across every row in the file, not just the desktop's, so this is
            # the same number a reader gets from settings-catalog.js's
            # SETTING_ROWS - one count, one meaning. The desktop-only figure is
            # beside it because that is the one the page and its markers care
            # about.
            "setting": sum(1 for r in rows if r["setting_row"]),
            "desktop_setting": sum(1 for r in desktop if r["setting_row"]),
        },
        "markers": {"begin": BEGIN, "end": END},
        "rows": rows,
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


KOTLIN_TEMPLATE = '''package com.jarvis.client.net

// GENERATED by tools/gen_settings_cases.py from backend/jarvis_settings_registry.py
// - do not edit by hand. Run `python3 tools/gen_settings_cases.py` after changing
// SETTINGS_ROWS; CI runs `--check`.
// SettingsCatalogTest holds this file to src/test/resources/contract/settings-cases.json.

/**
 * The settings switches on the phone's Settings screen whose words the PHONE owns.
 *
 * ONLY TWO ROWS ARE HERE, and that is the design (handoff section 3.3, "words
 * only, and only where the phone owns them"). For a row the PC owns - the
 * prompt coach is the one to remember - the phone must keep READING THE PC at
 * read time; swapping it for a string from here would fail
 * tools/check_parity.py rule 2, because /api/prompt/coach is classified `ported`
 * and the phone has to still call it.
 *
 * This is deliberately NOT a description of the Settings screen: SettingsScreen.kt's
 * LazyColumn is hand-written and stays that way. Use [row] for a row's own words,
 * and [ROWS]/[byPhoneKey] in a test for its key, section, order and apps.
 */
object SettingsCatalog {
    data class Row(
        val id: String,
        val setting: String?,
        val owner: String,
        val section: String,
        val order: Int,
        val label: String,
        val detail: String,
        val labelSpan: String?,
        val detailSpan: String?,
        /** True when the PC sends this row's visible words: the words above are a fallback. */
        val fallback: Boolean,
        /** False for the one toggle that is not a setting at all (the spending accept-all row). */
        val settingRow: Boolean,
        /** SettingsScreen.kt's own `item(key = ...)`, for the rows the phone has. */
        val phoneKey: String?,
        /** For a phone row, the Kotlin its words were copied from - by eye, not by a check. */
        val source: String?,
    )

    /** Shown when a row is missing - never silently blank. */
    const val MISSING = "This switch is not in your phone's settings list."

    val ROWS: List<Row> = listOf(
%(rows)s
    )

    private val BY_ID: Map<String, Row> = ROWS.associateBy { it.id }

    /** The rows that are really settings switches (not the spending accept-all row). */
    val SETTING_ROWS: List<Row> = ROWS.filter { it.settingRow }

    /** The rows whose visible words the PC sends: the words above are a fallback only. */
    val FALLBACK_ROWS: List<Row> = ROWS.filter { it.fallback }

    /** The row with this id, or null - callers keep their own fallback words. */
    fun row(id: String): Row? = BY_ID[id]

    /** The row the phone's own Settings screen shows under this key. */
    fun byPhoneKey(key: String): Row? = ROWS.firstOrNull { it.phoneKey == key }
}
'''


def kotlin_source(doc: dict) -> str:
    lines = []
    for r in doc["rows"]:
        null = "null"
        # `is not None`, not truthiness: `detail_span` is "" for the two rows
        # whose detail span carries no id, and that is NOT the same as a row
        # with no detail span (null). A truthiness test would merge the two.
        lines.append(
            "        Row({id}, {setting}, {owner}, {section}, {order}, {label}, {detail}, "
            "{ls}, {ds}, {fb}, {sr}, {pk}, {src}),".format(
                id=_kt(r["id"]),
                setting=_kt(r["setting"]) if r["setting"] else null,
                owner=_kt(r["owner"]),
                section=_kt(r["section"]),
                order=r["order"],
                label=_kt(r["label"]),
                detail=_kt(r["detail"]),
                ls=_kt(r["label_span"]) if r["label_span"] is not None else null,
                ds=_kt(r["detail_span"]) if r["detail_span"] is not None else null,
                fb=str(r["fallback"]).lower(),
                sr=str(r["setting_row"]).lower(),
                pk=_kt(r["phone_key"]) if r["phone_key"] else null,
                src=_kt(r["source"]) if r["source"] else null))
    return KOTLIN_TEMPLATE % {"rows": "\n".join(lines)}


def js_source(doc: dict) -> str:
    lines = [
        "// GENERATED by tools/gen_settings_cases.py from backend/jarvis_settings_registry.py",
        "// - do not edit by hand. Run `python3 tools/gen_settings_cases.py` after",
        "// changing SETTINGS_ROWS; CI runs `--check`.",
        "// tests/settings-catalogue.mjs holds this file to tests/fixtures/settings-cases.json",
        "// AND to the ids, words and row ORDER in src/settings.html.",
        "",
        f"export const SCHEMA = {json.dumps(doc['schema'])};",
        f"export const COUNTS = {json.dumps(doc['counts'], indent=2)};",
        f"export const MARKERS = {json.dumps(doc['markers'], indent=2)};",
        f"export const ROWS = {json.dumps(doc['rows'], indent=2)};",
        "",
        "/** The rows that are really settings switches (not the spending accept-all row). */",
        "export const SETTING_ROWS = ROWS.filter((r) => r.setting_row);",
        "",
        "/** The rows whose visible words the PC sends: the words here are a fallback only. */",
        "export const FALLBACK_ROWS = ROWS.filter((r) => r.fallback);",
        "",
        "/** The row with this id, or undefined. */",
        "export const row = (id) => ROWS.find((r) => r.id === id);",
        "",
    ]
    return "\n".join(lines)


def document() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------
#   Where the markers go, and at what indentation
# --------------------------------------------------------------------------

def _name(path: Path) -> str:
    """A path for a message: relative to the repository when it is inside it,
    and just the path itself when it is not (a test may point HTML somewhere
    else on purpose, and `relative_to` would raise instead of reporting)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _row_spans(html: str) -> list:
    """(start, end) of each toggle row in `html`, in page order - from the
    first character of its own line (the leading spaces included) through the
    end of the line its `</label>` is on.

    The leading spaces are part of the span on purpose: `markup` writes the
    row indented to `row.indent`, so the row read out of the page and the row
    rendered here are compared from the same first character, with no
    lstrip() on either side to hide an indentation mistake."""
    out = []
    for m in re.finditer(r'^[ \t]*<label[^>]*class="toggle[^"]*"[^>]*>[ \t]*$', html, re.M):
        s = m.start()
        e = html.index("</label>", m.end()) + len("</label>")
        e = html.index("\n", e) + 1      # through the end of that line
        out.append((s, e))
    return out


def _line_start(html: str, at: int) -> int:
    """The offset of the start of the line `at` sits on."""
    nl = html.rfind("\n", 0, at)
    return 0 if nl < 0 else nl + 1


def _indent_at(html: str, at: int) -> int:
    return at - _line_start(html, at)


def marker_indent() -> int:
    """The depth the BEGIN marker is written at: the first row's own."""
    return sorted(R.DESKTOP_ROWS, key=lambda r: r.order)[0].indent


def write_page() -> str:
    """The current settings.html, with the markers around its 26 toggle rows.

    Already spliced: handed straight back (the rows are regenerated by
    render_page). Not yet spliced: the markers are put around the rows the
    page really has, and EVERY row is first proved to be exactly what this
    table renders, at its own recorded depth - so the markers can never be
    placed around a set of rows that does not match, and the splice cannot
    silently rewrite the page."""
    html = HTML.read_text(encoding="utf-8")
    if BEGIN in html or END in html:
        if BEGIN not in html or END not in html:
            raise SystemExit(f"{_name(HTML)} has only one of the two markers")
        return html
    spans = _row_spans(html)
    if len(spans) != len(R.DESKTOP_ROWS):
        raise SystemExit(
            f"{_name(HTML)} has {len(spans)} toggle rows but "
            f"SETTINGS_ROWS describes {len(R.DESKTOP_ROWS)}")
    for row, (s, e) in zip(sorted(R.DESKTOP_ROWS, key=lambda r: r.order), spans):
        # WHICH row this is, not just whether it looks right: two rows swapped
        # on the page would otherwise each still match the OTHER's rendered
        # text when they happen to be shaped alike, and the swap would go
        # through. This is the identity check that makes the pairing meaningful.
        found = re.search(r'<input\b[^>]*\bid="([^"]+)"', html[s:e])
        if found is None or found.group(1) != row.dom_id:
            raise SystemExit(
                f"{_name(HTML)}: page order differs from SETTINGS_ROWS - "
                f"expected {row.dom_id!r} at position {row.order}, found "
                f"{found.group(1) if found else 'no <input> id'!r}")
        indent = _indent_at(html, s + len(html[s:e]) - len(html[s:e].lstrip(" ")))
        if indent != row.indent:
            raise SystemExit(f"{_name(HTML)}: row {row.order} ({row.dom_id}) is "
                             f"indented {indent} but SETTINGS_ROWS says {row.indent}")
        mine = markup(row, row.indent)
        if mine != html[s:e].rstrip("\n"):
            raise SystemExit(
                f"{_name(HTML)}: row {row.order} ({row.dom_id}) does not match "
                f"SETTINGS_ROWS.\n--- page ---\n{html[s:e].rstrip()}\n--- table ---\n{mine}")
    return _mark(html, spans)


def _mark(html: str, spans: list) -> str:
    """The two bare markers around the rows the page really has. The blank
    line the page keeps on either side of the first row is left where it is:
    the markers slot in against the rows, not against the blank lines."""
    indent = marker_indent()
    first, last = spans[0][0], spans[-1][1]
    return (html[:first] + " " * indent + BEGIN + "\n"
            + html[first:last]
            + " " * indent + END + "\n" + html[last:])



def render_page() -> str:
    """settings.html exactly as it must be: markers in place, every row
    written from the table at the depth the page has it at."""
    return splice(write_page(), indent=marker_indent())


def main() -> int:
    doc = document()
    page = render_page()
    kt = kotlin_source(build())
    js = js_source(build())
    targets = [(p, doc) for p in COPIES] + [(KOTLIN, kt), (JS_CATALOG, js), (HTML, page)]
    if "--check" in sys.argv:
        bad = []
        for p, text in targets:
            if p == HTML:
                # Read the page with universal newlines: git may hand this
                # checkout CRLF (the repository is LF), and a line-ending
                # difference is not a stale generated file.
                now = p.read_bytes().decode("utf-8").replace("\r\n", "\n") if p.exists() else ""
            else:
                now = p.read_text(encoding="utf-8") if p.exists() else None
            if now != text:
                bad.append(p)
        for p in bad:
            print(f"STALE {p.relative_to(ROOT)} - run python3 tools/gen_settings_cases.py")
        if not bad:
            print("settings-cases.json (both copies), SettingsCatalog.kt, settings-catalog.js "
                  "and settings.html's rows match")
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
