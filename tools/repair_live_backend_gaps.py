"""repair_live_backend_gaps.py - put back the three base-file pieces this PC's
install never received, without touching anything else.

WHY THIS EXISTS (measured 2026-10-30 on the owner's PC)

`main` is green and the deploy through `tools/reconcile_live_backend.py` moved
the live backend onto today's SHIPPED modules and HUD deltas with 0 refusals.
Three pieces still could not arrive, because they are **base-file / patch-carried** content that
only `scripts/apply-patches.ps1` would carry - and that patcher refuses 37
patches on this drifted install:

1. **jarvis_gate.py** - the two `_RISK` rows for the Android app builder
   (`app_build_android`, `app_install_android`). `jarvis-backend/jarvis_gate.py`
   (the published base) has them; the live file predates them. Without them
   `jarvis_gate.risk_for()` classifies the action as unknown, and a card for an
   unknown action is raised `approve_ok: false` - the owner cannot approve an
   app build at all (found in the field test: the card appeared but only Deny
   worked).
2. **jarvis_hud.py** - the `POST /api/history/pin` and
   `POST /api/history/archive` routes (added by later revisions of
   `chat-history.patch`). The live HUD's history route tuple ends at
   `/api/history/mark`, so both answer 404; the module `jarvis_chat_log.py`
   already has the handlers (it was synced by the deploy).
3. **jarvis_gate.py** - the card timer added by `show-card-timer.patch` (the
   owner's ruling of 2026-10-30: "if there is a card with a limited time of
   any kind, be sure to put the timer on it"). `pending()` never sends
   `expires_in` on this install, so no screen can draw a countdown and a
   routine card can still run out silently - the field test hit exactly that.

All three repairs are exact, anchored, idempotent edits. Nothing is guessed: if
an anchor is missing or appears more than once the tool refuses; if a repair is
already present it says so and writes nothing; every write is backed up first
and the result must compile or it is rolled back.

THE CARD TIMER IS TWO HUNKS, NOT ONE (measured 2026-10-30). The patch it copies
both inserts the `expires_in` block AND changes `pending()`'s SELECT line so the
row it reads has a `waited_until` column. A repair that inserts only the block
can never run - the column is not in the dict, `d.pop("waited_until", ...)` is
always None - and its own probes would still call it applied. So a `Repair` may
carry `extra_edits`: further exact old/new pairs applied in the SAME write,
with the same one backup and one compile. A file with only one of the hunks is
REFUSED rather than re-applied, so this tool can never duplicate the block.

This is a REPAIR for drifted installs, not a new mechanism to prefer: once the
patch stack can be applied again (`apply-patches.ps1` succeeds), the base files
carry both pieces and this tool reports "already" and does nothing.

USAGE

    python -B tools/repair_live_backend_gaps.py --backend-path "<live>"           # check only
    python -B tools/repair_live_backend_gaps.py --backend-path "<live>" --apply   # write (after a clean check)
    ... --only gate      # one repair
    ... --only history

Exit codes: 0 = every requested repair is present (or was applied);
1 = something is missing in check mode; 2 = refused (anchor missing/ambiguous,
or the rewritten file did not compile).
"""
from __future__ import annotations

import argparse
import py_compile
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Repair:
    """One anchored edit (one insertion, plus any `extra_edits`) in one live file."""

    name: str
    filename: str
    #: Every one of these strings must be in the file for the repair to count
    #: as already present.
    probes: tuple
    #: The exact text this repair replaces. It must appear exactly once, or
    #: the tool refuses.
    anchor: str
    #: What the anchor becomes. For an insertion this is the anchor plus the
    #: new lines; for a changed line it is the new line.
    replace_with: str
    why: str
    #: Further exact (old, new) text pairs applied in the SAME write as the
    #: anchor above - one backup, one compile, one swap. The card timer needs
    #: this: its patch has two functional hunks (the block, and the SELECT line
    #: that gives the block a column to read) and either one alone is a no-op.
    #: Each pair's old text must appear exactly once; its new text is the
    #: positive proof that pair is already in.
    extra_edits: tuple = ()


GATE_ROWS = Repair(
    name="gate",
    filename="jarvis_gate.py",
    probes=('"app_build_android": ("no"', '"app_install_android": ("no"'),
    anchor="_RISK: dict[str, tuple[str, str, str]] = {\n",
    replace_with=(
        "_RISK: dict[str, tuple[str, str, str]] = {\n"
        "    # tools/repair_live_backend_gaps.py (2026-10-30): the Android app\n"
        "    # builder's two cards. The published base has these rows; this install\n"
        "    # predates them, so the gate treated both actions as unclassified and\n"
        "    # refused to let their cards be approved. Copied from\n"
        "    # jarvis-backend/jarvis_gate.py byte for byte.\n"
        '    "app_build_android": ("no", "outbound", "runs Gradle on this PC in one task\'s own copy, and a first build downloads the Gradle distribution and the Android Gradle plugin from services.gradle.org, dl.google.com and repo.maven.apache.org - nothing of yours is sent, but build scripts are other people\'s code running with your own Windows permissions, and what they do cannot be taken back from here"),\n'
        '    "app_install_android": ("no", "local", "installs the .apk this build made onto your phone over its cable, replacing the copy already there; nothing reaches anyone else, but Jarvis has no uninstall button, so it stays on the phone until you remove it yourself"),\n'
    ),
    why="the app builder's approval cards are unapprovable without these rows",
)

HISTORY_ROUTES = Repair(
    name="history",
    filename="jarvis_hud.py",
    probes=("/api/history/pin", "/api/history/archive"),
    anchor='                     "/api/history/fork", "/api/history/mark"):\n',
    replace_with=(
        '                     "/api/history/fork", "/api/history/mark", "/api/history/pin",\n'
        '                     "/api/history/archive"):\n'
    ),
    why="pinning and archiving a chat answer 404 without these routes",
)

CARD_TIMER = Repair(
    name="timer",
    filename="jarvis_gate.py",
    probes=('d["expires_in"] = _whole', '_waited = d.pop("waited_until", None)'),
    anchor="        # Why this is being asked about at all, when the table said otherwise.\n",
    replace_with=(
        "        # 2026-10-30 (the owner's ruling: \"if there is a card with a limited\n"
        "        # time of any kind, be sure to put the timer on it\"): the request\n"
        "        # that bounds this card is shown to the screens as `expires_in`, in\n"
        "        # whole seconds, only while that request is still waiting. The card\n"
        "        # itself still has no deadline, nothing is refused because a clock\n"
        "        # reached zero, and the 60-second grace is never counted down (no\n"
        "        # request can act in it). Never 0, never negative; the remainder is\n"
        "        # rounded UP so a fraction of a second reads \"1s left\". A ceremony\n"
        "        # card carries no `waited_until` and keeps no timer. `waited_until`\n"
        "        # itself is dropped: the screens are told how long is left, never the\n"
        "        # PC's own clock reading. Copied from backend/show-card-timer.patch.\n"
        "        _waited = d.pop(\"waited_until\", None)\n"
        "        if _waited is not None:\n"
        "            try:\n"
        "                _secs_left = float(_waited) - time.time()\n"
        "            except (TypeError, ValueError):\n"
        "                _secs_left = 0.0\n"
        "            _whole = int(_secs_left)\n"
        "            if _secs_left > _whole:\n"
        "                _whole += 1\n"
        "            if _whole >= 1:\n"
        '                d["expires_in"] = _whole\n'
        "        # Why this is being asked about at all, when the table said otherwise.\n"
    ),
    #: The second half of backend/show-card-timer.patch (its SELECT hunk):
    #: pending() must ask for the column the block above reads. The patch keeps
    #: the SQL valid by splitting the one added string into two literals - the
    #: new column on the first line, `" FROM approvals"` on the second - so this
    #: is exactly that two-line post-image, not a one-line edit (which would
    #: compile and then fail at run time: "raised,waited_until WHERE ..." has no
    #: FROM clause). Without the column `d.pop("waited_until", None)` is always
    #: None - no screen ever gets an `expires_in`, which is a silent no-op this
    #: tool's probes would call applied. Same one write, one backup, one compile.
    extra_edits=(
        ('            "SELECT id,action,tier,detail,prompt,created,raised FROM approvals"\n',
         '            "SELECT id,action,tier,detail,prompt,created,raised,waited_until"\n'
         '            " FROM approvals"\n'),
    ),
    why="a card with a limited life cannot show its timer without both the "
        "inserted block and the SELECT column it reads",
)

REPAIRS = {r.name: r for r in (GATE_ROWS, HISTORY_ROUTES, CARD_TIMER)}


class Refused(Exception):
    pass


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="strict")


def check_one(live: Path, repair: Repair) -> str:
    """'already' or 'missing'. Raises Refused when the file/anchor is unusable.

    A repair with `extra_edits` is several hunks in one file, so a file holding
    only SOME of them is neither 'already' nor safe to insert again - re-running
    the insertion would put a second copy of the block in the live file. That
    half state is REFUSED; the card timer's two hunks (2026-10-30) are why.
    """
    p = live / repair.filename
    if not p.is_file():
        raise Refused(f"{repair.filename} is not in {live} - is this the live backend folder?")
    text = read(p)
    inserted = all(probe in text for probe in repair.probes)
    extras = [replacement in text for _old, replacement in repair.extra_edits]
    if inserted and all(extras):
        return "already"
    if inserted or any(extras):
        raise Refused(
            f"{repair.filename}: the {repair.name!r} repair is only PARTLY present "
            f"({'the inserted block' if inserted else 'a changed line'} is in, the "
            "rest is not). Refusing rather than writing it again and duplicating "
            "code; look at the file by hand.")
    if repair.anchor not in text:
        raise Refused(
            f"{repair.filename}: the anchor for {repair.name!r} is not there any more. "
            "Nothing was written; this install has drifted further and needs a real look.")
    if text.count(repair.anchor) != 1:
        raise Refused(
            f"{repair.filename}: the anchor for {repair.name!r} appears "
            f"{text.count(repair.anchor)} times; refusing to guess which one.")
    for old, _replacement in repair.extra_edits:
        if old not in text:
            raise Refused(
                f"{repair.filename}: the second anchor for {repair.name!r} is not "
                "there any more. Nothing was written; this install has drifted further.")
        if text.count(old) != 1:
            raise Refused(
                f"{repair.filename}: the second anchor for {repair.name!r} appears "
                f"{text.count(old)} times; refusing to guess which one.")
    return "missing"


def apply_one(live: Path, repair: Repair, *, stamp: str) -> str:
    """Apply the repair's hunks in one write, compiling before the swap sticks."""
    p = live / repair.filename
    state = check_one(live, repair)
    if state == "already":
        return "already"
    text = read(p)
    new = text.replace(repair.anchor, repair.replace_with, 1)
    for old, replacement in repair.extra_edits:
        new = new.replace(old, replacement, 1)
    backup = p.with_name(p.name + f".before-repair-{stamp}")
    shutil.copy2(p, backup)
    fd, tmpname = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(live))
    try:
        with open(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
        py_compile.compile(tmpname, doraise=True)
        shutil.move(tmpname, str(p))
    except Exception as exc:
        # Put the original back and remove the temporary, so the live folder is
        # never left in a half-written state.
        try:
            shutil.copy2(backup, p)
        finally:
            Path(tmpname).unlink(missing_ok=True)
        raise Refused(f"{repair.filename}: the repaired file did not compile "
                      f"({type(exc).__name__}); the original was restored") from exc
    return "applied"


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--backend-path", required=True,
                    help="the folder holding the live jarvis_hud.py")
    ap.add_argument("--apply", action="store_true",
                    help="write the repairs (without it this is a check)")
    ap.add_argument("--only", default="", choices=["", *REPAIRS.keys()],
                    help="repair only this one")
    ns = ap.parse_args(argv)
    live = Path(ns.backend_path).expanduser()
    chosen = [REPAIRS[ns.only]] if ns.only else list(REPAIRS.values())
    stamp = time.strftime("%Y%m%d-%H%M%S")
    outcomes = []
    try:
        for repair in chosen:
            state = check_one(live, repair)
            if state == "already":
                print(f"ok       {repair.name}: already present")
                outcomes.append("already")
                continue
            if not ns.apply:
                print(f"MISSING  {repair.name}: {repair.why}")
                outcomes.append("missing")
                continue
            applied = apply_one(live, repair, stamp=stamp)
            print(f"{'applied ' if applied == 'applied' else 'ok      '} {repair.name}: "
                  f"{repair.filename} ({'written, backup kept' if applied == 'applied' else 'already present'})")
            outcomes.append(applied)
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2
    if "missing" in outcomes:
        print("\nNothing was changed. Re-run with --apply after reviewing the above.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
