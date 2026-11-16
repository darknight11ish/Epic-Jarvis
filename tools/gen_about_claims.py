#!/usr/bin/env python3
"""Write the claims register's six totals into `docs/ABOUT-JARVIS.md`, from the register.

WHY THIS EXISTS. `docs/ABOUT-JARVIS.md` quotes the totals in `docs/CLAIMS.tsv`
in SIX places - the row count beside the register's name, the sentence spelling
out all four totals, the section 5 sentence about what is still open, the
section 6 table row, the checker's own summary line quoted verbatim, and the
"honest caution" about unverifiable rows. Every pull request that adds, closes
or re-flips a claim moves those totals, so every one of them had to hand-edit
the same six places. Three consecutive PRs did exactly that (`b24634c77`,
`f75b34e1f`, `9d70ec02b`), and the last one only exists because CI caught the
page stale: `backend/test_claims.py` counts the register and the page still
printed 268 / 256. A page whose numbers are typed by hand is a page that is
wrong between the typist and the next check.

THE OWNER'S RULING of 2026-11-15 08:35 (Q4): the six numbers are generated from
the register, in the shape this repository already uses for the two figures in
`docs/README.md` (`tools/gen_docs_map.py` writes them, `tools/check_docs_map.py`
is the gate).

WHAT IT DOES. It reads `docs/CLAIMS.tsv`, and rewrites ONLY the digits inside
those six statements. The wording, the backticks, the table pipes, the line
wrapping and every other byte of the page are left exactly as they were, so the
page keeps saying "still open" and the gate's patterns still match what this
tool wrote. It is idempotent: writing the numbers must leave the next run
nothing to write, and that is checked, not hoped for.

WHERE THE SIX SPOTS COME FROM - and this is the point of the shape. They are NOT
written down here. `backend/test_claims.py` already owns them, in
`ABOUT_COUNT_SPOTS`, and that is the table the required `backend` job uses to
fail a stale page. This tool imports that table, so there is ONE definition of
where the numbers live and a second copy cannot drift from the gate that judges
them. A page reworded past that table cannot be written by this tool, and this
tool says so instead of quietly writing nothing.

WHERE THE COUNTS COME FROM. `tools/check_claims.py`'s `read_register`, the same
function whose summary line section 6 quotes - so the quoted line cannot print
one thing while the checker prints another. The two readers are cross-checked
and this tool refuses to write when they disagree, so it can never produce a
page its own gate rejects. The figures are written without thousands
separators, because the checker prints them that way and the gate's patterns
capture `\\d+`.

HOW THE PAGE IS READ. Exactly the way the gate reads it: every run of whitespace
collapsed to one space (`" ".join(page.split())`), because one of the six
statements wraps across a line break. The match's position is then mapped back
to the page, so the digits are rewritten IN PLACE and no whitespace is touched.

WHAT IT REFUSES, loudly and without writing: a register it cannot read whole
(the checker would print no summary, so there would be no number to quote); a
register the two readers count differently; a page that no longer states one of
the six statements; and any result that a second pass would change again.

WHEN TO RUN IT. In the same pull request that changes `docs/CLAIMS.tsv`, before
pushing: `py -3 -B tools/gen_about_claims.py`, then commit the page with the
register. It is also what to run when the required `backend` job goes red with
"the page says (268, ...) docs/CLAIMS.tsv holds (269, ...)". `--check` is safe
anywhere - it writes nothing - and is what a test proves.

Run:  py -3 -B tools/gen_about_claims.py            # write the register's numbers
      py -3 -B tools/gen_about_claims.py --check    # write nothing; fail and
                                                    # print every number that differs
Exit: 0 when the page states the register's totals (and reads them the way the
      gate does), 1 otherwise, naming what differs or what it could not write.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent

#: The page whose six numbers this writes, and the register they are taken from.
PAGE = ROOT / "docs" / "ABOUT-JARVIS.md"
REGISTER = ROOT / "docs" / "CLAIMS.tsv"

#: The gate that already fails a stale page, and whose `ABOUT_COUNT_SPOTS` table
#: says where the six statements are. Imported, never copied - see the docstring.
GATE = ROOT / "backend" / "test_claims.py"

#: The checker whose summary line section 6 quotes, and whose register reader
#: decides what the four figures are.
CHECKER = TOOLS / "check_claims.py"

#: The three states a register row may carry, in the order the page quotes them.
STATES = ("built", "open", "unverifiable")

#: How a statement missing from the page is reported. `main` uses it to tell
#: "the page stopped stating this number" - which no write can fix, so the tool
#: refuses - from "the page states the wrong number", which is its whole job.
MISSING = "nothing on the page states"


class RegisterUnreadable(Exception):
    """The register cannot be counted, so there is no honest number to write."""


def _load(name: str, path: Path):
    """One module, loaded by path: this tool shares the code, never a copy."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gate():
    """`backend/test_claims.py` - the page's gate and its table of six spots."""
    return _load("gen_about_claims_gate", GATE)


def checker():
    """`tools/check_claims.py` - the register's reader."""
    return _load("gen_about_claims_checker", CHECKER)


def counts(register: Path, module=None) -> dict[str, int]:
    """The totals `tools/check_claims.py` prints, counted from the register.

    `rows` is what the summary calls "claim(s) checked"; the other three are its
    `built`, `still open` and `unverifiable` figures. `read_register` is the
    same function that prints that summary, so the quotation in the page cannot
    say something the checker does not.
    """
    module = module or checker()
    rows, problems = module.read_register(Path(register))
    if problems:
        raise RegisterUnreadable(
            f"{register} cannot be read whole, so the checker would print no "
            f"summary and there is no total to quote: " + "; ".join(problems[:3]))
    if not rows:
        raise RegisterUnreadable(f"{register} holds no rows at all")
    out = {"rows": len(rows)}
    for state in STATES:
        out[state] = sum(1 for row in rows if row["state"] == state)
    return out


def gate_counts(register: Path, module=None) -> dict[str, int]:
    """The same totals, counted the way `backend/test_claims.py` counts them.

    The gate measures the page's truth with its OWN tiny reader (`data_rows`)
    rather than the checker's parser, on purpose. This tool writes numbers the
    gate compares against, so it refuses when the two readers disagree instead
    of writing a page the required `backend` job would reject.
    """
    module = module or gate()
    rows = module.data_rows(Path(register).open(encoding="utf-8", newline="").read())
    out = {"rows": len(rows)}
    for state in STATES:
        out[state] = sum(1 for row in rows if row.get("state") == state)
    return out


def flatten(text: str) -> tuple[str, list[int]]:
    """(flat, offsets): the page as the gate reads it, and where each character is.

    `backend/test_claims.py` joins the page's whitespace runs into single spaces
    before it looks for its six statements, and one of them wraps across a line
    break - section 5's "And 7 of / the 269 claims" does. So this tool reads the
    page the same way, and `offsets` maps every flattened character back to its
    position in the page, so a match can be rewritten in place without touching
    a single space.
    """
    flat: list[str] = []
    offsets: list[int] = []
    index, size = 0, len(text)
    while index < size:
        if text[index].isspace():
            end = index
            while end < size and text[end].isspace():
                end += 1
            if not flat or end == size:       # " ".join(...) drops both ends
                index = end
                continue
            flat.append(" ")
            offsets.append(index)
            index = end
            continue
        flat.append(text[index])
        offsets.append(index)
        index += 1
    return "".join(flat), offsets


def statements(page: str, module=None) -> list[dict]:
    """Every place the page states one of the register's totals.

    One entry per match of the gate's own table, in the table's order, with the
    source span of each captured figure so `render_page` can rewrite exactly the
    digits and `problems` can say which line is wrong. The values are integers,
    so "1,000" and "1000" are the same figure; this tool writes them without a
    separator because the checker prints `1000` and the gate captures `\\d+`.
    """
    module = module or gate()
    flat, offsets = flatten(page)
    found: list[dict] = []
    for name, pattern, fields in module.ABOUT_COUNT_SPOTS:
        for match in re.finditer(pattern, flat):
            spans = []
            for index in range(1, len(fields) + 1):
                start, end = match.span(index)
                if start < 0:                 # a group the pattern does not fill
                    raise RuntimeError(
                        f"{name}: group {index} did not take part in the match - "
                        f"this tool cannot tell which number it would be writing")
                spans.append((offsets[start], offsets[end - 1] + 1))
            found.append({
                "name": name,
                "fields": tuple(fields),
                "values": tuple(int(match.group(i))
                                for i in range(1, len(fields) + 1)),
                "line": page.count("\n", 0, spans[0][0]) + 1,
                "spans": tuple(spans),
                "span": (offsets[match.start()], offsets[match.end() - 1] + 1),
            })
    return found


def problems(page: str, values: dict[str, int],
             module=None) -> tuple[list[str], list[dict]]:
    """(every way `page` disagrees with `values`, the statements it found)."""
    module = module or gate()
    found = statements(page, module)
    out: list[str] = []
    for name, _pattern, _fields in module.ABOUT_COUNT_SPOTS:
        if not any(entry["name"] == name for entry in found):
            out.append(f"{MISSING} {name!r} any more - it was "
                       f"reworded past backend/test_claims.py's own pattern, so "
                       f"re-anchor that table and this tool together rather than "
                       f"leaving the number unwritten")
    for entry in found:
        for field, got in zip(entry["fields"], entry["values"]):
            if got != values[field]:
                out.append(f"line {entry['line']}: {entry['name']} says "
                           f"{field}={got}; the register holds {field}={values[field]}")
    return out, found


def render_page(page: str, values: dict[str, int], module=None) -> str:
    """`page` with only the digits inside its six statements set to `values`.

    Nothing else is touched and nothing moves: every edit replaces one run of
    digits with another, so the wording, the whitespace and the page's own
    length are the writer's, not this tool's.
    """
    module = module or gate()
    edits = []
    for entry in statements(page, module):
        for field, (start, end) in zip(entry["fields"], entry["spans"]):
            edits.append((start, end, str(values[field])))
    edits.sort()
    out: list[str] = []
    at = 0
    for start, end, new in edits:
        if start < at:
            raise RuntimeError(f"two statements overlap at character {start}; this "
                               f"tool cannot write one number as two")
        out.append(page[at:start])
        out.append(new)
        at = end
    out.append(page[at:])
    return "".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Write the claims register's totals into docs/ABOUT-JARVIS.md, "
                    "in the six statements backend/test_claims.py already checks.")
    parser.add_argument("--page", default=str(PAGE),
                        help="the page to write (default: <repo>/docs/ABOUT-JARVIS.md)")
    parser.add_argument("--register", default=str(REGISTER),
                        help="the register to count (default: <repo>/docs/CLAIMS.tsv)")
    parser.add_argument("--check", action="store_true",
                        help="write nothing; fail and print every number that differs")
    args = parser.parse_args(argv)

    page_path = Path(args.page)
    register_path = Path(args.register)
    for path in (page_path, register_path):
        if not path.is_file():
            print(f"gen about claims FAILED: {path} is missing")
            return 1

    module = gate()
    try:
        values = counts(register_path)
    except RegisterUnreadable as err:
        print(f"gen about claims FAILED: {err}")
        return 1
    theirs = gate_counts(register_path, module)
    if values != theirs:
        print("gen about claims FAILED: tools/check_claims.py and "
              f"backend/test_claims.py count {register_path} differently "
              f"({values} against {theirs}) - one of them misreads the register, "
              "and no page can agree with both")
        return 1

    original = page_path.open(encoding="utf-8", newline="").read()
    diffs, found = problems(original, values, module)
    for name, _pattern, _fields in module.ABOUT_COUNT_SPOTS:
        seen = sum(1 for entry in found if entry["name"] == name)
        print(f"{'found' if seen else 'none '} {name}: {seen} spot(s)")

    missing = [line for line in diffs if line.startswith(MISSING)]
    if missing:
        for line in missing:
            print(f"WARN  {line}")
        print("gen about claims FAILED: the page no longer states every one of the "
              "register's six statements, so this tool cannot keep it true - correct "
              "the page's wording, or the table it is read with")
        return 1

    if args.check:
        if diffs:
            print(f"gen about claims FAILED: {len(diffs)} number(s) on {page_path} "
                  f"disagree with {register_path}:")
            for line in diffs:
                print(f"  {line}")
            print("run it without --check and commit what it writes")
            return 1
        print(f"gen about claims OK: {page_path} already states the register's "
              f"{values['rows']} rows: {values['built']} built, {values['open']} "
              f"still open, {values['unverifiable']} unverifiable")
        return 0

    if not diffs:
        print("gen about claims: nothing to change")
    else:
        rendered = render_page(original, values, module)
        # Idempotence, checked rather than hoped for: writing the numbers must
        # leave the next run nothing to write.
        if render_page(rendered, values, module) != rendered:
            print("gen about claims FAILED: a second pass over its own output would "
                  "change the page again - the six statements are not a fixed point; "
                  "report this rather than committing it")
            return 1
        left, _found = problems(rendered, values, module)
        if left:
            print("gen about claims FAILED: the page it built still disagrees with "
                  "the register, so it writes nothing:")
            for line in left:
                print(f"  {line}")
            return 1
        page_path.open("w", encoding="utf-8", newline="").write(rendered)
        # What is on disk is what decides, not what was in memory.
        if page_path.open(encoding="utf-8", newline="").read() != rendered:
            print(f"gen about claims FAILED: wrote {page_path} but read back "
                  f"something else")
            return 1
        print(f"gen about claims: wrote {page_path}")
        for line in diffs:
            print(f"  {line}")

    print(f"gen about claims: {values['rows']} rows, {values['built']} built, "
          f"{values['open']} still open, {values['unverifiable']} unverifiable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
