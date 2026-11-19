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

AND ONE STALE VALUE (found on the owner's PC, 2026-11-18)

The restraint above - NEVER overwrite a line the owner already has - is right
for a setting that is a CHOICE. It is wrong for a value that names something the
code does not have any more. The owner's file still said:

    degrade_chain = ["jarvis-escalate", "jarvis-bulk", "jarvis-critic"]

months after the owner's 2026-10-27 decision collapsed the three cloud lanes
into ONE (`jarvis-escalate`; `jarvis-bulk` and `jarvis-critic` do not exist in
the code). The repository's own `rebuilt/jarvis-framework.toml` has been right
since that decision, and that is why the normal path cannot deliver it: the
patcher keeps every line of an existing file, so a corrected value reaches a
FRESH install and never the owner's. `jarvis_router.degrade()` now drops a name
it cannot serve (so the stale line can no longer send a rate-limited turn to a
lane that is not there), and this script makes the file itself honest again:

  * ONLY `[budget] degrade_chain`, and ONLY when a name in it is one this PC
    cannot serve: a name outside the shipped chain and outside the configured
    local model (`[intelligence] default_model`). Every name it does serve is
    left exactly as written, so a shorter chain the owner chose is untouched.
  * The line is replaced with the SHIPPED chain, whole, preserving its indent,
    its comment-free shape and the file's line endings. Every other byte is
    copied through.
  * If the key is absent, empty or split over several lines it is left alone and
    a plain sentence says so - a rewrite this script is not certain about is a
    rewrite it does not make.
  * Same verification and backup as the tier merge; both repairs are ONE write.
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


def config_of(path: Path) -> dict:
    """The whole file, parsed - the tier table is no longer the only thing read."""
    reader = toml_reader()
    if reader is None:
        raise RuntimeError("no TOML reader (tomllib/tomli) in this Python")
    return reader.loads(path.read_bytes().decode("utf-8-sig"))


BUDGET_TABLE = "[budget]"


def chain_of(cfg: dict) -> list:
    """`[budget] degrade_chain` as a list, or [] for absent/a different shape."""
    got = (cfg.get("budget") or {}).get("degrade_chain")
    return list(got) if isinstance(got, list) else []


def serviceable_names(live_cfg: dict, shipped_chain: list) -> set:
    """Lane names this PC can really serve in a degrade chain.

    The shipped chain is the code's own answer for "which cloud lane exists"
    (it is `["jarvis-escalate"]` since the 2026-10-27 decision), and the local
    model is the floor every chain can legitimately name. Anything else is a
    name from a config older than the code - it cannot be a lane, whatever the
    file says.
    """
    names = {str(n) for n in shipped_chain}
    local = str((live_cfg.get("intelligence") or {}).get("default_model") or "")
    if local:
        names.add(local)
    return names


def repair_chain(text: str, live_cfg: dict, shipped_cfg: dict) -> tuple:
    """(new text, names removed, why it could not be done safely).

    ONE line, inside `[budget]`, replaced whole. Everything else is copied.
    """
    shipped_chain = chain_of(shipped_cfg)
    live_chain = chain_of(live_cfg)
    if not shipped_chain or not live_chain:
        return text, [], ""
    allowed = serviceable_names(live_cfg, shipped_chain)
    dead = [str(n) for n in live_chain if str(n) not in allowed]
    if not dead:
        return text, [], ""
    # Find the ONE `degrade_chain = ...` line in the [budget] table. A comment
    # naming it, a key in another table, or a value split across lines is not
    # something this script rewrites - it says so instead.
    hits, section = [], ""
    for i, line in enumerate(text.splitlines(keepends=True)):
        if opens_a_table(line):
            section = line.strip()
            continue
        if section == BUDGET_TABLE and re.match(r"^[ \t]*degrade_chain\s*=", line):
            hits.append(i)
    lines = text.splitlines(keepends=True)
    if len(hits) != 1:
        return text, dead, ("[budget] has %d degrade_chain line(s), so rewriting one "
                            "would not be safe" % len(hits))
    i = hits[0]
    body = lines[i].rstrip("\r\n")
    ending = lines[i][len(body):]
    if not body.rstrip().endswith("]"):
        return text, dead, ("degrade_chain is not written on one line, so rewriting "
                            "it would not be safe")
    indent = body[:len(body) - len(body.lstrip(" \t"))]
    new_line = (indent + "degrade_chain = ["
                + ", ".join('"%s"' % n for n in shipped_chain) + "]" + ending)
    return "".join(lines[:i]) + new_line + "".join(lines[i + 1:]), dead, ""


def _flatten(cfg: dict, prefix: str = "") -> dict:
    """Every non-table key of a parsed config as dotted paths, for one compare."""
    out = {}
    for key, value in cfg.items():
        path = "%s.%s" % (prefix, key) if prefix else str(key)
        if isinstance(value, dict):
            out.update(_flatten(value, path))
        else:
            out[path] = value
    return out


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
           added: dict, repaired_chain=None) -> str:
    """Empty when the result is good, else the sentence to print and write nothing.

    Read back with the same reader the backend uses: what is checked is the
    FILE, not the string this script just built. Every setting the file had is
    compared by its dotted path, so the tier merge and the one degrade_chain
    repair are the only two things that can have changed.
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
    flat_before, flat_after = _flatten(before_cfg), _flatten(after_cfg)
    expected = set(flat_before) | {"autonomy.tiers.%s" % k for k in added}
    if repaired_chain is not None:
        expected.add("budget.degrade_chain")
    if set(flat_after) != expected:
        missing = sorted(expected - set(flat_after))
        extra = sorted(set(flat_after) - expected)
        return "a setting would appear or disappear (%s%s)" % (
            "missing: " + ", ".join(missing) if missing else "",
            ("; " if missing and extra else "") +
            ("unexpected: " + ", ".join(extra) if extra else ""))
    for path, old in flat_before.items():
        if path == "budget.degrade_chain" and repaired_chain is not None:
            continue
        if flat_after.get(path) != old:
            return "a setting would change (%s: %r -> %r)" % (
                path, old, flat_after.get(path))
    if repaired_chain is not None and flat_after.get("budget.degrade_chain") != repaired_chain:
        return ("degrade_chain read back as %r, not %r"
                % (flat_after.get("budget.degrade_chain"), repaired_chain))
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
        shipped_cfg = config_of(SHIPPED)
        live_cfg = config_of(live_path)
        shipped = (shipped_cfg.get("autonomy") or {}).get("tiers") or {}
        live = (live_cfg.get("autonomy") or {}).get("tiers") or {}
    except Exception as exc:                             # noqa: BLE001
        print("Could not read the settings: %s" % exc)
        return 2

    raw = live_path.read_bytes()
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")
    added = {k: v for k, v in shipped.items() if k not in live}
    repaired_text, dead, chain_why = repair_chain(text, live_cfg, shipped_cfg)
    # A rewrite this script is not certain about is a rewrite it does not make.
    # That is said loudly but does not fail the update: the router already
    # refuses a name it cannot serve, so the stale line is cosmetic from here.
    if chain_why:
        print("degrade_chain names a lane this PC does not have (%s), but %s. "
              "That line was left exactly as it is."
              % (", ".join(str(n) for n in dead), chain_why))
        repaired_text, dead = text, []
    if not added and not dead:
        print("Nothing to add: %s already has a line for all %d shipped tiers."
              % (live_path.name, len(shipped)))
        return 0

    new_text, keys, why = merge(repaired_text, live, shipped)
    if why:
        print("Refusing: %s. Nothing was changed." % why)
        return 2
    expected_chain = chain_of(shipped_cfg) if dead else None
    problem = verify(text, new_text, live, {k: shipped[k] for k in keys},
                     expected_chain)
    if problem:
        print("Refusing: %s. Nothing was changed." % problem)
        return 2

    if dead:
        print("Stale in %s - these [budget] degrade_chain names are not lanes "
              "this PC has:" % live_path.name)
        for name in dead:
            print("    - %s" % name)
        print("    -> %s" % ("[" + ", ".join('"%s"' % n for n in expected_chain) + "]"))
    if keys:
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
    if keys:
        print("Added %d tier(s) to: %s" % (len(keys), live_path))
    if dead:
        print("Fixed the stale [budget] degrade_chain line in: %s" % live_path)
        print("Removed name(s) this PC does not have: %s" % ", ".join(dead))
    print("Your copy from before the change: %s" % kept)
    print("To undo it, copy that file back over jarvis-framework.toml.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
