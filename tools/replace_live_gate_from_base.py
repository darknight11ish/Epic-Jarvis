#!/usr/bin/env python3
"""replace_live_gate_from_base.py - replace ONE drifted live `jarvis_gate.py`
with the published base, once, with the old file kept.

WHY THIS EXISTS (the owner's ruling, Q3, 2026-11-25)

`C:\\Users\\pcadmin\\Documents\\Claude\\Open jarvis files\\Desktop program\\
jarvis_gate.py` measured 236,453 bytes on 2026-11-19 and is a lineage the
repair tool cannot recognise - `tools/repair_live_backend_gaps.py` refuses it
by hash. Hand-patching new rows into a file whose lineage nobody can identify
is how a gate ends up with two versions of the same table and no way to say
which one runs. The ruling is: **diff first, upstream any valid live-only
fix, then replace cleanly from the repo base.** Never hand-patch rows into an
unrecognised lineage.

This tool is the third step. It is deliberately small and deliberately
one-shot:

  * it REFUSES unless the live file is byte for byte the one that was
    diffed for this pull request - `LIVE_GATE_SHA256` below;
  * it REFUSES unless the base it would write is byte for byte the one that
    was classified - `BASE_GATE_SHA256` below;
  * it copies the live file to `jarvis_gate.py.bak.<date>` beside itself,
    and never overwrites an existing backup;
  * it writes the base bytes and verifies the result's own SHA-256;
  * it RE-IMPORTS the written file in a subprocess (never in this process)
    and asserts the two rows the live gate never had: the cardless
    `cancel_scheduled` tool row and `github_mode`'s risk + tool rows. A model
    that does not answer both is refused and the backup is put back.

THE BASE IS A PUBLISHED SNAPSHOT, BUT IT NOW CARRIES THE APPROVAL MODEL THE
LIVE GATE HAS. It was copied out of the owner's backend on 2026-10-06 and has
been grown by hand since; the live gate is that program plus the patch stack's
later hunks. Measured for the 2026-11-26 replacement, the base did NOT carry
the 2026-10-28 request-bounding machinery (`waited_until`, `_wait_open`,
`_expire_overdue`, `still_waiting`) or the 2026-10-30 card timer, so writing it
would have destroyed them. The same day's second change put all of that INTO
the base and retired the three patches that carried it
(`no-expiry-cards.patch`, `no-deadline-cards.patch`,
`show-card-timer.patch`), so the file this tool writes keeps the model the
owner's install has. `approval_model_note()` still measures what the base
actually carries and says so before a write; with today's base the note is
empty because there is nothing to warn about.

This tool does NOT apply patches either. Measured 2026-11-26 over the 59
`jarvis_gate.py` patches that remain in the stack: 58 do not apply to the
published base, and 56 of the 62 then-current ones did not apply to the live
file, so neither is "the patch stack's pre-image". The replacement is a lineage
reset onto the file the repository publishes, and new gate rows reach it
through `jarvis-backend/jarvis_gate.py` +
`tools/repair_live_backend_gaps.py`, not through a new patch.

WHY THE HASHES ARE IN THE FILE AND NOT A FLAG. A flag would make the guard
optional, and a guard that can be waved through is not a guard. Re-measuring
the live file means editing this file, which is a reviewed diff; that is the
friction the ruling asks for. `--allow-new-base` exists only because `main`
moves: a newer published base is still a reviewed file, but it is not the one
this tool's diff classified, so the owner has to say so out loud.

USAGE

    py -3 tools/replace_live_gate_from_base.py --backend-path "<live>"          # check only
    py -3 tools/replace_live_gate_from_base.py --backend-path "<live>" --apply  # write

Exit codes: 0 = the live gate is already the base, or was replaced and
re-imported cleanly; 2 = refused (wrong hash, wrong base, an existing backup,
the write did not verify, or the re-import check failed - in which case the
backup has been put back).

Proven by `backend/test_replace_live_gate_from_base.py`, which builds every
case in a temp folder: the refusal writes nothing, the backup holds the old
bytes, the written file is the base and imports, and a base without the two
rows is rolled back.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

#: The published base this tool writes. `jarvis-backend/` is what an installer
#: starts from, so a live install brought to it is a recognised lineage again.
DEFAULT_BASE = REPO / "jarvis-backend" / "jarvis_gate.py"

#: The ONE live gate this replacement was measured against (2026-11-19,
#: 236,453 bytes). Anything else is refused - including a later file that
#: merely looks similar.
LIVE_GATE_SHA256 = (
    "c2a31981d7863c1a08e2200cc208c8f0950bead1503d40614cbcaa0ce06a2f95"
)

#: The base that was diffed against it (232,674 bytes when the 2026-11-26
#: replacement was measured; 254,865 bytes / 4,146 lines after the same day's
#: second change put the 2026-10-28 request-bounding machinery and the
#: 2026-10-30 card timer INTO the base, and its two now-historical comments were
#: corrected). A moved base needs `--allow-new-base`, which says so in the
#: output.
BASE_GATE_SHA256 = (
    "9d8bae0d0db25a3870b2accbafa18d2681832b995cb054002a7c2a4005a23a9d"
)

#: The rows the replacement must prove are there after the write. They are
#: base content the live gate never received: `cancel_scheduled` is the
#: cardless cancel, and `github_mode` is the mode's own card. The subprocess
#: check reads them from the imported module, not from the text.
_MUST_HAVE = ("cancel_scheduled", "github_mode")

#: Runs in a SEPARATE interpreter: the only way to know the file that now sits
#: on disk is importable and carries the rows, rather than the module this
#: process already imported (or a stale one on sys.path).
_REIMPORT_CHECK = r"""
import json
import os
import sys

live_dir = sys.argv[1]
sys.path.insert(0, live_dir)
import jarvis_gate as g

target = os.path.join(live_dir, "jarvis_gate.py")
imported = os.path.abspath(getattr(g, "__file__", ""))
tools = getattr(g, "_TOOL_ACTIONS", {}) or {}
risk = getattr(g, "_RISK", {}) or {}
facts = {
    "imported": imported,
    "cancel_scheduled": tools.get("cancel_scheduled"),
    "github_mode_tool": tools.get("github_mode"),
    "github_mode_risk": bool(risk.get("github_mode")),
    "action_cancel_scheduled": g.action_for_tool("cancel_scheduled")[0],
    "action_github_mode": g.action_for_tool("github_mode")[0],
}
print(json.dumps(facts))
problems = []
if imported != os.path.abspath(target):
    problems.append("imported %s, not the written file" % imported)
if facts["cancel_scheduled"] != "auto":
    problems.append("cancel_scheduled tool row is %r" % (facts["cancel_scheduled"],))
if facts["github_mode_tool"] != "github_mode":
    problems.append("github_mode tool row is %r" % (facts["github_mode_tool"],))
if not facts["github_mode_risk"]:
    problems.append("github_mode has no _RISK row")
if facts["action_cancel_scheduled"] != "cancel_scheduled":
    problems.append("action_for_tool('cancel_scheduled') is %r"
                    % (facts["action_cancel_scheduled"],))
if facts["action_github_mode"] != "github_mode":
    problems.append("action_for_tool('github_mode') is %r"
                    % (facts["action_github_mode"],))
if problems:
    raise SystemExit("re-import check failed: " + "; ".join(problems))
"""


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _identity(path: Path) -> dict:
    raw = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(raw),
        "lines": len(raw.splitlines()),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _line_delta(old: bytes, new: bytes) -> tuple[int, int]:
    """(added, removed) line counts, for the one-line change summary."""
    a = old.decode("utf-8", "replace").splitlines()
    b = new.decode("utf-8", "replace").splitlines()
    added = removed = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    return added, removed


def approval_model_note(base_bytes: bytes) -> str:
    """What approval model the base carries, measured from its own bytes.

    The base is a published snapshot, and the request-bounding rewrite of
    2026-10-28/30 used to be patch-carried. Since 2026-11-26 the published
    base CARRIES it, so the state this warns about is only reachable by
    `--allow-new-base` naming an older base on purpose - and then the warning
    is the difference between a replacement and a surprise.
    """
    if b"waited_until" in base_bytes:
        return ""
    return ("NOTE: this base carries the older countdown model - `pending()` "
            "counts a card down from `created` and stale rows are swept only "
            "at start-up. The 2026-10-28 read-time sweep, the no-deadline "
            "ceremonies, `still_waiting()` and the 2026-10-30 card timer are "
            "NOT in it. They are base content since 2026-11-26, so an older "
            "base was named with --allow-new-base and this write would replace "
            "them.")


def reimport_check(live_dir: Path) -> tuple[bool, str]:
    """Import the written gate in a subprocess and ask for the two rows."""
    proc = subprocess.run(
        [sys.executable, "-I", "-c", _REIMPORT_CHECK, str(live_dir)],
        capture_output=True, text=True,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return False, (out + "\n" + err).strip() or f"exit {proc.returncode}"
    try:
        facts = json.loads(out.splitlines()[-1])
    except Exception as exc:  # noqa: BLE001 - the subprocess is foreign input
        return False, f"could not read the check's answer ({exc}): {out}"
    wanted = {
        "cancel_scheduled": "auto",
        "github_mode_tool": "github_mode",
        "action_cancel_scheduled": "cancel_scheduled",
        "action_github_mode": "github_mode",
    }
    wrong = [f"{key}={facts.get(key)!r} (wanted {value!r})"
             for key, value in wanted.items() if facts.get(key) != value]
    if not facts.get("github_mode_risk"):
        wrong.append("github_mode has no _RISK row")
    if wrong:
        return False, "missing after the write: " + "; ".join(wrong)
    return True, out


def replace_gate(
    backend_path: str | os.PathLike,
    *,
    base_path: str | os.PathLike = DEFAULT_BASE,
    expected_live_sha: str = LIVE_GATE_SHA256,
    expected_base_sha: str = BASE_GATE_SHA256,
    apply: bool = False,
    allow_new_base: bool = False,
    day: str | None = None,
    out=print,
) -> int:
    """The whole operation. Returns 0 for ok/no-op, 2 for a refusal."""
    live_dir = Path(backend_path)
    live = live_dir / "jarvis_gate.py"
    base = Path(base_path)
    if not live.is_file():
        out(f"REFUSED: no `{live}`. Nothing was written.")
        return 2
    if not base.is_file():
        out(f"REFUSED: the base `{base}` is missing. Nothing was written.")
        return 2

    before = _identity(live)
    base_id = _identity(base)
    out(f"live: {before['bytes']:,} B / {before['lines']:,} lines  "
        f"sha256 {before['sha256']}")
    out(f"base: {base_id['bytes']:,} B / {base_id['lines']:,} lines  "
        f"sha256 {base_id['sha256']}")

    if before["sha256"] != expected_live_sha:
        out("REFUSED: the live gate is not the file this replacement was "
            "measured against. Nothing was written.")
        out(f"  expected sha256 {expected_live_sha}")
        out(f"  found    sha256 {before['sha256']}")
        out("  Diff it and record the new hash in this tool (and the PR) "
            "before running it.")
        return 2

    if base_id["sha256"] != expected_base_sha:
        if not allow_new_base:
            out("REFUSED: the published base moved since this replacement was "
                "measured, so a different file would be written. Nothing was "
                "written.")
            out(f"  expected sha256 {expected_base_sha}")
            out(f"  found    sha256 {base_id['sha256']}")
            out("  Re-run the classification, or pass --allow-new-base to say "
                "out loud that the newer published base is the one to write.")
            return 2
        out("NOTE: the base moved; writing the newer published base because "
            "--allow-new-base was given.")

    if before["sha256"] == base_id["sha256"]:
        out("ok: the live gate is already the published base byte for byte; "
            "nothing to do.")
        return 0

    added, removed = _line_delta(live.read_bytes(), base.read_bytes())
    out(f"change: +{added:,} / -{removed:,} lines; the two rows the live gate "
        f"never had are `{_MUST_HAVE[0]}` and `{_MUST_HAVE[1]}`.")
    note = approval_model_note(base.read_bytes())
    if note:
        out(note)

    if not apply:
        out("check only: nothing was written. Re-run with --apply to write "
            "the base and keep the backup.")
        return 0

    day = day or date.today().isoformat()
    backup = live_dir / f"jarvis_gate.py.bak.{day}"
    if backup.exists():
        out(f"REFUSED: `{backup.name}` already exists. A backup is never "
            "overwritten, and nothing was written.")
        return 2

    original = live.read_bytes()
    shutil.copy2(live, backup)
    if _sha(backup) != before["sha256"]:
        out(f"REFUSED: the backup `{backup.name}` did not copy cleanly; the "
            "live gate was not touched.")
        return 2
    out(f"backup: {backup}  (sha256 {before['sha256']})")

    tmp = live.with_name(live.name + ".replacing")
    try:
        tmp.write_bytes(base.read_bytes())
        os.replace(tmp, live)
    except Exception as exc:  # noqa: BLE001 - restore, then report
        if tmp.exists():
            tmp.unlink()
        live.write_bytes(original)
        out(f"REFUSED: the write failed ({exc}); the live gate was put back.")
        return 2

    written = _identity(live)
    if written["sha256"] != base_id["sha256"]:
        live.write_bytes(original)
        out("REFUSED: the written file is not the base byte for byte; the "
            f"live gate was put back from `{backup.name}`.")
        return 2
    out(f"wrote: {written['bytes']:,} B / {written['lines']:,} lines  "
        f"sha256 {written['sha256']}")

    ok, detail = reimport_check(live_dir)
    if not ok:
        live.write_bytes(original)
        out("REFUSED: the written gate failed the re-import check, so the "
            f"live gate was put back from `{backup.name}`.")
        out(f"  {detail}")
        return 2
    out("re-import: a fresh interpreter imported the written file and found "
        f"`{_MUST_HAVE[0]}` (cardless) and `{_MUST_HAVE[1]}` (its own risk and "
        "tool rows).")
    out("NEXT: the live gate is now the published base, which carries the "
        "2026-10-28 request-bounding machinery and the 2026-10-30 card timer. "
        "New gate rows reach it through jarvis-backend/jarvis_gate.py + "
        "tools/repair_live_backend_gaps.py, not through a new patch.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Replace a drifted live jarvis_gate.py with the published "
                    "base, once, with a backup and a re-import check.")
    ap.add_argument("--backend-path", required=True,
                    help="the live backend folder (holds jarvis_gate.py)")
    ap.add_argument("--apply", action="store_true",
                    help="write the base; without it the tool only checks")
    ap.add_argument("--allow-new-base", action="store_true",
                    help="write the current published base even though it is "
                         "not the one this tool was measured against")
    args = ap.parse_args(argv)
    return replace_gate(args.backend_path, apply=args.apply,
                        allow_new_base=args.allow_new_base)


if __name__ == "__main__":
    sys.exit(main())
