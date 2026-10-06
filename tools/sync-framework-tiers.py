"""Bring jarvis-framework.toml's [autonomy.tiers] up to the shipped defaults.

    python tools\\sync-framework-tiers.py                 # show what would change
    python tools\\sync-framework-tiers.py --apply          # do it
    python tools\\sync-framework-tiers.py --apply "D:\\path\\jarvis-framework.toml"

Written 2026-10-03, after a run of the suites showed the live config and the
code disagreeing. It lives in `tools/` because it runs from THIS REPOSITORY
against the owner's file, the same as every other tool here - it is never
copied into the backend folder, and backend/test_shipped_modules.py would
(rightly) fail if a script like this sat in `backend/` without being shipped.

WHY THIS IS NEEDED

`apply-patches.ps1` deliberately NEVER overwrites jarvis-framework.toml:
it holds decisions only the owner makes. But the code has grown new
`[autonomy.tiers]` entries over weeks, and none of them ever reaches an
existing file. A name that is not in that table takes `unknown_action_tier`
- "ask" in the shipped config - so nothing fails OPEN, but:

  * a documented `"auto"` read (calendar_read, email_read, notes_search,
    home_read, news_read, page_read, github_read, append_obsidian_daily) asks
    the owner every single time instead;
  * the suites compare the live config with the shipped one and report the
    disagreement as a product failure, which is what happened on 2026-10-03
    (test_agent.py's draft_email/tidy_inbox cases); and worst,
  * a name the SHIPPED file declares as "ask" and the live file declares
    LOOSER becomes a real problem, guarded only by each module's own
    belt-and-braces check. `draft_email = "auto"` in the live file is exactly
    that: jarvis_asks_first.HARD_LIMITS says it must never be "auto".

WHAT IT DOES, AND HOW CAREFULLY

  * MISSING keys are APPENDED with the shipped value.
  * An existing key is never relaxed. If the live file is STRICTER than the
    shipped one, it is left alone and reported - an owner may always choose
    to be asked more.
  * An existing key that is LOOSER than the shipped one, where the shipped
    value is the specific tier "ask", is CORRECTED, one line at a time, and
    every correction is printed. Anything looser than that is reported and
    NOT changed unless it is one of those "ask" cases: loosening away from
    "ask" is the shape of a real hole, so it is named loudly instead.
  * It reads and writes BYTES: line endings, a BOM and any non-ASCII
    characters survive exactly as they are.
  * It refuses to write unless the result PARSES and reads back exactly the
    tiers it intended, with every other top-level section unchanged.
  * It writes a timestamped copy of the original and prints its path.
  * `--apply` is required. With no flag it only prints.

The shipped defaults come from `backend/rebuilt/jarvis-framework.toml`, the
same file apply-patches.ps1 installs, so there is one source of truth.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

#: This file lives in tools/, so the backend is one directory up.
BACKEND = Path(__file__).resolve().parent.parent / "backend"
SHIPPED = BACKEND / "rebuilt" / "jarvis-framework.toml"
DEFAULT_LIVE = Path(
    r"C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
    r"\jarvis-framework.toml")

TABLE = "[autonomy.tiers]"


def toml_reader():
    try:
        import tomllib
        return tomllib
    except ImportError:
        try:
            import tomli
            return tomli
        except ImportError:
            return None


def tiers_of(path: Path) -> dict:
    reader = toml_reader()
    if reader is None:
        raise RuntimeError("no TOML reader (tomllib/tomli) available")
    cfg = reader.loads(path.read_bytes().decode("utf-8-sig"))
    return (cfg.get("autonomy") or {}).get("tiers") or {}


def opens_a_table(line: str) -> bool:
    """A "[name]" inside a comment is prose, not a table - and these files'
    own comments mention [autonomy.tiers] and [tools]."""
    s = line.strip()
    return s.startswith("[") and not s.startswith("#")


def tiers_span(text: str):
    """(header_start, body_start, body_end) for [autonomy.tiers], or None."""
    m = re.compile(r"^\[autonomy\.tiers\][ \t]*$", re.M).search(text)
    if not m:
        return None
    body_start = m.end()
    rest = text[body_start:]
    offset = 0
    for line in rest.split("\n"):
        if opens_a_table(line):
            return m.start(), body_start, body_start + offset
        offset += len(line) + 1
    return m.start(), body_start, len(text)


def main(argv) -> int:
    apply = "--apply" in argv
    args = [a for a in argv[1:] if not a.startswith("--")]
    live_path = Path(args[0]) if args else DEFAULT_LIVE

    if not live_path.is_file():
        print("No file at: %s" % live_path)
        return 2
    if not SHIPPED.is_file():
        print("This repository has no %s - get a fresh copy." % SHIPPED)
        return 2

    shipped = tiers_of(SHIPPED)
    raw = live_path.read_bytes()
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in text else "\n"
    live = tiers_of(live_path)

    print("live file:    %s" % live_path)
    print("shipped file: %s" % SHIPPED)
    print("tiers: live %d, shipped %d" % (len(live), len(shipped)))

    # _rank is weakest-first, so a LOWER rank is the looser one. Getting this
    # the wrong way round files a loosening as "stricter, left alone", which
    # is the opposite of the point.
    missing = {k: v for k, v in shipped.items() if k not in live}
    looser = {k: (live[k], shipped[k]) for k in live
              if k in shipped and live[k] != shipped[k]
              and _rank(live[k]) < _rank(shipped[k])}
    stricter = {k: (live[k], shipped[k]) for k in live
                if k in shipped and live[k] != shipped[k]
                and _rank(live[k]) > _rank(shipped[k])}

    print()
    print("missing here:        %d" % len(missing))
    for k in sorted(missing):
        print("    + %-34s %r" % (k, missing[k]))
    print("looser than shipped: %d" % len(looser))
    for k in sorted(looser):
        print("    ! %-34s live=%r shipped=%r" % (k, looser[k][0], looser[k][1]))
    print("stricter (kept):     %d" % len(stricter))
    for k in sorted(stricter):
        print("    = %-34s live=%r (left alone)" % (k, stricter[k][0]))

    # Loosening AWAY from "ask" is the dangerous shape. Correct only the
    # specific case the shipped file pins to "ask"; report anything else.
    correct = {}
    shout = {}
    for k, (lv, sv) in looser.items():
        (correct if sv == "ask" else shout)[k] = (lv, sv)
    if shout:
        print()
        print("!!! NOT CHANGED - these are looser than the shipped default and")
        print("!!! the shipped default is not the specific tier \"ask\". Read them:")
        for k, (lv, sv) in sorted(shout.items()):
            print("!!! %-34s live=%r shipped=%r" % (k, lv, sv))

    if not missing and not correct:
        print()
        print("Nothing to change - the live file already matches the shipped defaults.")
        return 0

    span = tiers_span(text)
    if span is None:
        print("The live file has no [autonomy.tiers] line of its own - not touching it.")
        return 2
    _hdr_start, body_start, body_end = span
    if not text[:body_end].endswith("\n"):
        print("Refusing: the [autonomy.tiers] body does not end at a line boundary.")
        return 2

    new_text = text
    done_correct = []
    for k in sorted(correct):
        pat = re.compile(r"^([ \t]*%s[ \t]*=[ \t]*)\"[^\"]*\"([ \t]*(?:#.*)?)$"
                         % re.escape(k), re.M)
        m = pat.search(new_text)
        if not m:
            print("Could not find the exact line for %s - not touching it." % k)
            return 2
        new_text = new_text[:m.start()] + '%s"ask"%s' % (m.group(1), m.group(2)) \
            + new_text[m.end():]
        done_correct.append(k)

    if missing:
        # Recompute the body end in the (possibly corrected) text.
        body_end2 = tiers_span(new_text)[2]
        block = nl + ("# Added %s by tools/sync-framework-tiers.py: entries this\n"
                      "# repository's rebuilt/jarvis-framework.toml has had, which the\n"
                      "# live file was missing. A missing line means \"ask\"\n"
                      "# (unknown_action_tier) - so without these the reads below asked\n"
                      "# every time. Each value is the shipped default; yours is never\n"
                      "# relaxed.\n" % time.strftime("%Y-%m-%d"))
        for k in sorted(missing):
            block += "%s = %r%s" % (k.ljust(33), missing[k], nl)
        new_text = new_text[:body_end2] + block + new_text[body_end2:]

    reader = toml_reader()
    try:
        before_cfg = reader.loads(text)
        after_cfg = reader.loads(new_text)
    except Exception as exc:  # noqa: BLE001
        print("Refusing: the result would not parse (%s). Nothing was changed." % exc)
        return 2

    after = (after_cfg.get("autonomy") or {}).get("tiers") or {}
    for k, v in missing.items():
        if after.get(k) != v:
            print("Refusing: %s read back as %r, not %r." % (k, after.get(k), v))
            return 2
    for k in done_correct:
        if after.get(k) != "ask":
            print("Refusing: %s read back as %r, not 'ask'." % (k, after.get(k)))
            return 2
    # Everything else must be exactly as it was.
    for k, v in live.items():
        if k not in done_correct and after.get(k) != v:
            print("Refusing: existing tier %s would change (%r -> %r)."
                  % (k, v, after.get(k)))
            return 2
    if sorted(before_cfg) != sorted(after_cfg):
        print("Refusing: a top-level section would appear or disappear.")
        return 2

    print()
    if not apply:
        print("DRY RUN - nothing written. Re-run with --apply to make these changes.")
        print("  would append %d tier(s)" % len(missing))
        print("  would correct %d tier(s): %s" % (len(done_correct), ", ".join(done_correct)))
        return 0

    backup = live_path.with_name(
        "%s.backup-%s" % (live_path.name, time.strftime("%Y-%m-%d-%H%M%S")))
    out = new_text.encode("utf-8")
    if bom:
        out = b"\xef\xbb\xbf" + out
    try:
        live_path.write_bytes(out)
    except OSError as exc:  # noqa: BLE001
        print("Could not write %s (%s). Nothing was changed." % (live_path, exc))
        return 2
    try:
        backup.write_bytes(raw)
        kept = str(backup)
    except OSError as exc:  # noqa: BLE001
        kept = "(could not be written: %s)" % exc

    print("Checked first: the result parses, every intended tier reads back, and")
    print("every other tier is unchanged.")
    print()
    print("Written: %s" % live_path)
    print("  appended %d tier(s)" % len(missing))
    if done_correct:
        print("  corrected %d tier(s) to \"ask\": %s"
              % (len(done_correct), ", ".join(done_correct)))
    print()
    print("Your copy from before the change: %s" % kept)
    print("To undo it, copy that file back over jarvis-framework.toml.")
    return 0


def _rank(tier: str) -> int:
    """Weakest first. An unrecognised tier is treated as strictest, the same
    direction jarvis_gate._tiers() refuses to unlock on a typo."""
    return {"auto": 0, "notify": 1, "ask": 2, "never": 3}.get(str(tier).lower(), 4)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
