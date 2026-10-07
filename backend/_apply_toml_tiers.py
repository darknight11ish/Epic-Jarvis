"""Add the repository's missing [autonomy.tiers] lines to a live config.

    py -3 backend\\_apply_toml_tiers.py --apply [<the owner's jarvis-framework.toml>]

    (no --apply: print what it would add, write nothing)

WHY THIS EXISTS (found on the owner's PC, 2026-10-06)

`scripts/apply-patches.ps1` has never overwritten `jarvis-framework.toml`: it
holds decisions only the owner makes (tiers, [tools].enabled, notes folders),
so the script copies this repository's file in ONLY when there is none, and
otherwise prints `backend/_config_diff.py`'s difference and changes nothing.

That restraint is right, and it has one hole. A patch adds an ACTION, and the
action's tier is a line in `[autonomy.tiers]` - a line that reaches a fresh
install and never an existing one. A tier line that is not there is not a
crash: the gate resolves the action through `unknown_action_tier` ("ask" as
shipped). Fail-safe, and still the wrong answer twice over:

  * a documented "auto" READ (calendar_read, email_read, page_read, ...) asks
    the owner EVERY time instead - `tools/sync-framework-tiers.py`'s own
    docstring says this; and
  * the update ends `DONE WITH PROBLEMS`. `test_gate_names.py` compares the
    live table with the shipped one, and `test_agent.py` resolves each tool
    through the gate, so two new actions that arrived in a pull request
    (2026-10-06: `read_web_page` and `chat_card_pin`) failed four checks on
    the owner's machine while the repository was entirely correct. The tests
    were right; the config never caught up.

WHAT IT DOES

  * Reads the repository's shipped `rebuilt/jarvis-framework.toml` and the
    live file, and APPENDS the value of every `[autonomy.tiers]` key the live
    file is missing, at the END of the live file's `[autonomy.tiers]` block,
    with the shipped value spelled out (`read_web_page = "ask"`). Appending
    the SHIPPED value is the one choice that cannot loosen anything: a missing
    tier is "ask", and the only shipped value that is not "ask" makes the
    action HARDER, not easier.
  * NEVER touches a key that is already in the live file, whatever it says.
    An owner may always choose to be asked more, and a live value that is
    LOOSER than the shipped one is `tools/sync-framework-tiers.py`'s decision
    to report, not this script's to make.
  * Touches no other section and no other line: it inserts text at one point
    and copies every other byte through, so comments, blank lines, the order
    of the tiers, a BOM and CRLF endings all survive exactly.
  * Refuses to write unless the result PARSES, every added key reads back as
    the value intended, every existing key is unchanged, and every top-level
    section the file had is still there. Any of those failing and nothing is
    written at all.
  * Writes a timestamped copy beside the live file before it writes, and
    prints its path. Plain standard library (tomllib on 3.11+).
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

#: .../backend/_apply_toml_tiers.py -> .../backend, and the same file
#: apply-patches.ps1 installs when the owner has none.
BACKEND = Path(__file__).resolve().parent
SHIPPED = BACKEND / "rebuilt" / "jarvis-framework.toml"

TABLE = "[autonomy.tiers]"


def toml_reader():
    try:
        import tomllib
        return tomllib
    except ImportError:                                  # Python < 3.11
        try:
            import tomli                                # type: ignore
            return tomli
        except ImportError:
            return None


def tiers_of(path: Path) -> dict:
    reader = toml_reader()
    if reader is None:
        raise RuntimeError("no TOML reader (tomllib/tomli) in this Python")
    cfg = reader.loads(path.read_bytes().decode("utf-8-sig"))
    return (cfg.get("autonomy") or {}).get("tiers") or {}


def opens_a_table(line: str) -> bool:
    """A "[name]" inside a comment is prose, not a table - and this file's own
    comments mention [autonomy.tiers] and [tools]."""
    s = line.strip()
    return s.startswith("[") and not s.startswith("#")


def tiers_span(text: str):
    """(body_start, body_end) for [autonomy.tiers], or None if it has none.

    The end is the start of the next line that opens a table, or the end of
    the file - the same walk tools/sync-framework-tiers.py makes.

    `\\r?` before the `$`: the owner's file is written on Windows, and without
    it the table header of a CRLF file never matches at all - the merge then
    reports "no [autonomy.tiers] line of its own" about a file that plainly
    has one. (Found by this script's own suite, which runs it on CRLF.)
    """
    m = re.compile(r"^\[autonomy\.tiers\][ \t]*\r?$", re.M).search(text)
    if not m:
        return None
    body_start = m.end()
    offset = 0
    for line in text[body_start:].split("\n"):
        if opens_a_table(line):
            return body_start, body_start + offset
        offset += len(line) + 1
    return body_start, len(text)


def merge(live_text: str, live: dict, shipped: dict) -> tuple:
    """(the new text, the keys added, a plain sentence why not).

    Adds nothing but a line per missing key: every other byte is copied."""
    missing = {k: v for k, v in shipped.items() if k not in live}
    if not missing:
        return live_text, [], ""
    span = tiers_span(live_text)
    if span is None:
        return live_text, [], ("the live file has no [autonomy.tiers] line of its "
                               "own, so there is nowhere to add them")
    _body_start, body_end = span
    if not live_text[:body_end].endswith("\n"):
        return live_text, [], ("the [autonomy.tiers] body does not end at a line "
                               "boundary, so adding a line there is not safe")
    nl = "\r\n" if "\r\n" in live_text else "\n"
    block = nl.join([
        "# Added %s by scripts/apply-patches.ps1 (backend/_apply_toml_tiers.py):"
        % time.strftime("%Y-%m-%d"),
        "# actions this repository's rebuilt/jarvis-framework.toml has a tier for,",
        "# which this file was missing. A missing line means \"ask\"",
        "# (unknown_action_tier); each value below is the shipped one and is never",
        "# looser than that. Nothing already here is changed.",
    ]) + nl
    for k in sorted(missing):
        block += '%s = "%s"%s' % (k.ljust(33), missing[k], nl)
    return live_text[:body_end] + block + live_text[body_end:], sorted(missing), ""


def verify(before_text: str, after_text: str, live: dict,
           added: dict) -> str:
    """Empty when the result is good, else the sentence to print and write nothing.

    Read back with the same reader the backend uses: what is checked is the
    FILE, not the string this script just built.
    """
    reader = toml_reader()
    try:
        before_cfg = reader.loads(before_text)
        after_cfg = reader.loads(after_text)
    except Exception as exc:                             # noqa: BLE001
        return "the result would not parse (%s)" % exc
    after = (after_cfg.get("autonomy") or {}).get("tiers") or {}
    for k, v in added.items():
        if after.get(k) != v:
            return "%s read back as %r, not %r" % (k, after.get(k), v)
    for k, v in live.items():
        if after.get(k) != v:
            return "an existing tier would change (%s: %r -> %r)" % (k, v, after.get(k))
    if sorted(before_cfg) != sorted(after_cfg):
        return "a top-level section would appear or disappear"
    return ""


def main(argv) -> int:
    apply = "--apply" in argv
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        print("Which file? Give the jarvis-framework.toml to add the lines to.")
        return 2
    live_path = Path(args[0])
    if not live_path.is_file():
        print("No file at: %s" % live_path)
        return 2
    if not SHIPPED.is_file():
        print("This repository has no %s - get a fresh copy." % SHIPPED)
        return 2
    try:
        shipped = tiers_of(SHIPPED)
        live = tiers_of(live_path)
    except Exception as exc:                             # noqa: BLE001
        print("Could not read the tiers: %s" % exc)
        return 2

    raw = live_path.read_bytes()
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")
    added = {k: v for k, v in shipped.items() if k not in live}
    if not added:
        print("Nothing to add: %s already has a line for all %d shipped tiers."
              % (live_path.name, len(shipped)))
        return 0

    new_text, keys, why = merge(text, live, shipped)
    if why:
        print("Refusing: %s. Nothing was changed." % why)
        return 2
    problem = verify(text, new_text, live, {k: shipped[k] for k in keys})
    if problem:
        print("Refusing: %s. Nothing was changed." % problem)
        return 2

    print("Missing from %s (%d):" % (live_path, len(keys)))
    for k in keys:
        print('    + %-34s "%s"' % (k, shipped[k]))
    if not apply:
        print("DRY RUN - nothing written. Add --apply to make these changes.")
        return 0

    out = new_text.encode("utf-8")
    if bom:
        out = b"\xef\xbb\xbf" + out
    backup = live_path.with_name(
        "%s.backup-%s" % (live_path.name, time.strftime("%Y-%m-%d-%H%M%S")))
    # The copy is written FIRST, and the live file only after it is safely on
    # disk - which is what the docstring above promises ("before it writes").
    # It used to be the other way round: the live file was overwritten, then
    # the copy attempted. A failure between the two (no space, a locked file,
    # power loss) therefore left the approval-tier table changed with no undo
    # copy, and the very next line still printed "Your copy from before the
    # change: <path>" for a file that did not exist.
    try:
        backup.write_bytes(raw)
        kept = str(backup)
    except OSError as exc:                               # noqa: BLE001
        print("Could not write the backup %s (%s). "
              "Nothing was changed." % (backup, exc))
        return 2
    try:
        live_path.write_bytes(out)
    except OSError as exc:                               # noqa: BLE001
        print("Could not write %s (%s). Nothing was changed - the copy from "
              "before the change is %s." % (live_path, exc, kept))
        return 2
    print("Checked first: the result parses, every added tier reads back, every other")
    print("tier and every other section is unchanged.")
    print("")
    print("Added %d tier(s) to: %s" % (len(keys), live_path))
    print("Your copy from before the change: %s" % kept)
    print("To undo it, copy that file back over jarvis-framework.toml.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
