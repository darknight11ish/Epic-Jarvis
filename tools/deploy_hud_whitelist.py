#!/usr/bin/env python3
"""deploy_hud_whitelist.py - rehearse, and with --apply perform, the STATIC_ASSETS
deploy onto a live `jarvis_hud.py`, refusing any drift first.

WHY THIS EXISTS
    On 2026-10-25 sixteen `STATIC_ASSETS` keys - the browser HUD's face page and
    the fifteen modules it loads - were hand-inserted into the owner's live
    install (400,287 -> 402,720 bytes) so the HUD server could serve the real
    face. The argument that this was safe was a MEASUREMENT: the live file's 27
    existing whitelist entries matched the published base's values exactly. A
    measurement is true until the next edit. This tool makes it the condition
    the write depends on, and refuses when it stops being true.

WHAT IT DOES
    Reads the live file named on the command line and the published base
    (`jarvis-backend/jarvis_hud.py`) at `--ref` (default `origin/main`), then
    compares the two `STATIC_ASSETS` dictionaries:

      * REFUSES (exit 1, nothing written) when the live table has a key the base
        does not, or a key whose value differs. That is the drift the
        hand-insertion argument does not cover.
      * REFUSES when `STATIC_ASSETS` is not exactly one module-level literal
        dict, when a key is duplicated, or when the closing brace is not alone
        on its line. The insertion point comes from the AST, never from string
        surgery, so a whole-line pure insertion is the only write possible.
      * DRY RUNS by default: prints the exact lines it would insert, where they
        go, and the target's expected byte and line delta. It changes nothing.
      * With `--apply`, after `ast.parse` and `compile()` of the new text, keeps
        a timestamped `<file>.before-<date>` backup, writes through a temp file
        beside the target and one `os.replace` (a single atomic step), then
        reads the file back: a fresh interpreter compiles it and its whitelist
        is compared with the base again. Any failed read-back restores the
        original bytes. It never imports the module (importing it would start
        the server).
      * `--verify-live FOLDER` only checks that the live folder's
        `STATIC_ASSETS` carries the sixteen face keys and that every served
        file they name exists beside the server. No network, no git, no write.

    The insertion copies only the base's missing ENTRY lines (key and value);
    comments around them in the base are not carried, and no other line of the
    live file is touched - the tool proves the new text is the old text with
    one insertion before it writes anything.

WHAT IT DOES NOT DO
    It does not copy the served files and it does not restart anything: the
    whitelist is only half of the face deploy (`tools/reconcile_live_backend.py`
    copies the files). It never fetches (a missing ref is an error with the
    fix), never reads or writes a token, never talks to the running server, and
    never writes unless `--apply` says so.

Run:
    py -3 tools/deploy_hud_whitelist.py "C:/.../jarvis_hud.py"            # dry run
    py -3 tools/deploy_hud_whitelist.py "C:/.../jarvis_hud.py" --apply    # write
    py -3 tools/deploy_hud_whitelist.py --verify-live "C:/.../Desktop program"
"""
from __future__ import annotations

import argparse
import ast
import datetime as _dt
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

#: The repository root (the tool lives in <root>/tools/).
ROOT = Path(__file__).resolve().parent.parent
#: The published base, relative to the repository root, read from `--ref`.
BASE_RELPATH = "jarvis-backend/jarvis_hud.py"
DEFAULT_REF = "origin/main"

#: The browser HUD's face page. The face section of the base table starts here.
FACE_ANCHOR = "/faces.html"
#: The face page and the fifteen modules it loads - the sixteen files #814 added
#: to the whitelist, and the set `--verify-live` requires. Kept equal to the
#: base table's own face section by backend/test_deploy_hud_whitelist.py, so a
#: change there fails a check instead of silently under-verifying a deploy.
FACE_KEYS = (
    "/faces.html",
    "/faces-spec.js",
    "/face-pace.js",
    "/critter-pose.js",
    "/critter-owl.js",
    "/critter-otter.js",
    "/critter-monkey.js",
    "/critter-robot.js",
    "/critters-gen.js",
    "/lipsync.js",
    "/sky.js",
    "/season.js",
    "/face-words.js",
    "/jarvis-link.js",
    "/card-words.js",
    "/replace-confirm.js",
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: A fresh interpreter reads the file from disk and compiles it. No import: an
#: import of jarvis_hud would start the server as a side effect.
_COMPILE_CODE = (
    "import pathlib, sys\n"
    "p = pathlib.Path(sys.argv[1])\n"
    "compile(p.read_bytes(), str(p), 'exec')\n"
)


class Refused(Exception):
    """A condition the tool will not write through. Nothing has been changed."""


@dataclass(frozen=True)
class Assets:
    """One parsed `STATIC_ASSETS` table and the AST node it came from."""

    source: str
    assets: dict
    node: ast.Dict


@dataclass(frozen=True)
class Plan:
    """The exact change, or the proof that there is nothing to change."""

    live: Path
    base_label: str
    old_bytes: bytes
    new_bytes: bytes
    missing: tuple
    insertion: str
    offset: int
    anchor_line: int
    old_lines: int
    new_lines: int
    live_assets: dict
    expected_assets: dict


# --------------------------------------------------------------------- read --

def _decode(raw: bytes, label: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Refused(f"{label} is not valid UTF-8 ({exc}); refusing to compare "
                      "text this tool cannot read") from None


def _base_from_ref(ref: str, repo: Path) -> tuple:
    """The published base's bytes at `ref`, and the label to print. Never fetches."""
    if not ref or ref.startswith("-") or any(ch.isspace() for ch in ref):
        raise OSError(f"refusing an empty or option-like --ref {ref!r}")
    spec = f"{ref}:{BASE_RELPATH}"
    proc = subprocess.run(["git", "-C", str(repo), "show", spec],
                          capture_output=True)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        last = detail[-1] if detail else "git show failed"
        raise OSError(f"cannot read {spec} from {repo}: {last}. "
                      "Run `git fetch origin` - this tool never fetches.")
    return proc.stdout, spec


def find_static_assets(source: str, label: str) -> Assets:
    """The one module-level `STATIC_ASSETS = {...}` literal, or `Refused`.

    Exactly one plain assignment is required: two would make the anchor
    ambiguous, a `dict(...)` call or an annotated assignment cannot be compared
    with the base, and a duplicate key would make the table mean two things.
    """
    try:
        tree = ast.parse(source, filename=label)
    except SyntaxError as exc:
        raise Refused(f"{label} does not parse: {exc.msg} (line {exc.lineno})") from None
    found = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "STATIC_ASSETS"
                for target in node.targets):
            found.append(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == "STATIC_ASSETS":
            found.append(node)
    if not found:
        raise Refused(f"{label} has no module-level STATIC_ASSETS assignment")
    if len(found) != 1:
        lines = ", ".join(str(node.lineno) for node in found)
        raise Refused(f"{label} has {len(found)} module-level STATIC_ASSETS "
                      f"assignments (lines {lines}); exactly one is required "
                      "because the insertion anchor would be ambiguous")
    node = found[0]
    if isinstance(node, ast.AnnAssign):
        raise Refused(f"{label}: STATIC_ASSETS is an annotated assignment "
                      f"(line {node.lineno}); only a plain "
                      "`STATIC_ASSETS = {...}` can be edited")
    value = node.value
    if not isinstance(value, ast.Dict):
        raise Refused(f"{label}: STATIC_ASSETS is not a dict literal "
                      f"(line {node.lineno}); it cannot be compared or safely "
                      "inserted into")
    seen = set()
    for key in value.keys:
        if key is None:
            raise Refused(f"{label}: STATIC_ASSETS has a `**` unpacking entry "
                          f"(line {node.lineno}); it cannot be compared safely")
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            raise Refused(f"{label}: STATIC_ASSETS has a non-string literal key "
                          f"(line {key.lineno}); refusing to guess what it is")
        if key.value in seen:
            raise Refused(f"{label}: STATIC_ASSETS has duplicate key "
                          f"{key.value!r} (line {key.lineno}); the table would "
                          "be ambiguous")
        seen.add(key.value)
    try:
        assets = ast.literal_eval(value)
    except (ValueError, TypeError) as exc:
        raise Refused(f"{label}: STATIC_ASSETS is not a literal dict of "
                      f"literals ({exc}); refusing to compare it") from None
    if not isinstance(assets, dict):
        raise Refused(f"{label}: STATIC_ASSETS did not evaluate to a dict")
    return Assets(source=source, assets=assets, node=value)


# --------------------------------------------------------------------- plan --

def _anchor(assets: Assets, label: str) -> tuple:
    """(byte offset of the closing-brace line, 1-based line number, line ending).

    The anchor must be a lone `}` line: its only content before the brace is
    indentation and nothing follows it. That is what makes "insert the entries
    immediately before this line" a pure insertion with no other code in reach.
    """
    lines = assets.source.splitlines(keepends=True)
    index = (assets.node.end_lineno or 0) - 1
    if index < 0 or index >= len(lines):
        raise Refused(f"{label}: cannot locate the STATIC_ASSETS closing brace")
    raw = lines[index]
    body = raw.rstrip("\r\n")
    end_col = assets.node.end_col_offset
    if end_col is None or end_col < 1 or end_col > len(body) \
            or body[end_col - 1] != "}":
        raise Refused(f"{label}: line {index + 1} is not the STATIC_ASSETS "
                      f"closing brace this tool can anchor on ({body!r})")
    if body[:end_col - 1].strip() or body[end_col:].strip():
        raise Refused(f"{label}: the STATIC_ASSETS closing brace on line "
                      f"{index + 1} is not alone on its line ({body!r}); a pure "
                      "insertion there could touch other code, so nothing was "
                      "changed")
    ending = raw[len(body):]
    if not ending:
        ending = "\r\n" if "\r\n" in assets.source else "\n"
    return sum(len(line) for line in lines[:index]), index + 1, ending


def _live_indent(assets: Assets) -> str:
    """The indentation the live table already gives its entries."""
    if not assets.node.keys:
        return "    "
    line = assets.source.splitlines()[assets.node.keys[0].lineno - 1]
    return line[:len(line) - len(line.lstrip())]


def _insertion(base: Assets, missing: tuple, live_indent: str,
               ending: str) -> str:
    """The missing entries as source lines, in base order, with live indentation.

    Each entry is exactly the base's own source text for its key and value (via
    `ast.get_source_segment`, so a multi-line value stays as valid source); a
    trailing comma is added when the base's own does not cover it.
    """
    picked = []
    for key_node, value_node in zip(base.node.keys, base.node.values):
        try:
            key = ast.literal_eval(key_node)
        except (ValueError, TypeError):
            continue
        if key not in missing:
            continue
        key_src = ast.get_source_segment(base.source, key_node)
        value_src = ast.get_source_segment(base.source, value_node)
        if not key_src or not value_src:
            raise Refused(f"cannot read the base source for key {key!r}; "
                          "refusing to guess the entry")
        entry = f"{live_indent}{key_src}: {value_src},"
        picked.extend(entry.replace("\r\n", "\n").split("\n"))
    if not picked:
        raise Refused("the base has missing keys but none could be rendered; "
                      "nothing was changed")
    return "".join(line + ending for line in picked)


def _drift_text(live_only: list, differing: list, live_assets: dict,
                base_assets: dict) -> str:
    lines = [f"the live whitelist is not a subset of the base: "
             f"{len(live_only)} key(s) exist only in live and "
             f"{len(differing)} value(s) differ."]
    for key in live_only[:10]:
        lines.append(f"live only: {key!r} -> {live_assets[key]!r}")
    if len(live_only) > 10:
        lines.append(f"... and {len(live_only) - 10} more live-only key(s)")
    for key, live_value, base_value in differing[:10]:
        lines.append(f"differs: {key!r}: live {live_value!r} "
                     f"!= base {base_value!r}")
    if len(differing) > 10:
        lines.append(f"... and {len(differing) - 10} more differing value(s)")
    lines.append("The hand insertion of 2026-10-25 was safe only because every "
                 "key the live table already had matched the published base. This "
                 "tool refuses when that is no longer true.")
    lines.append("Reconcile the live file first (tools/reconcile_live_backend.py) "
                 "or restore it, then re-run. Nothing was changed.")
    return "\n".join(lines)


def make_plan(live: Path, base_source: str, base_label: str) -> Plan:
    """Read `live`, compare it with the base, and build (but never write) the change."""
    old_bytes = live.read_bytes()
    live_source = _decode(old_bytes, str(live))
    live_assets = find_static_assets(live_source, str(live))
    base_assets = find_static_assets(base_source, base_label)

    live_only = [key for key in live_assets.assets
                 if key not in base_assets.assets]
    differing = [(key, live_assets.assets[key], base_assets.assets[key])
                 for key in live_assets.assets
                 if key in base_assets.assets
                 and live_assets.assets[key] != base_assets.assets[key]]
    if live_only or differing:
        raise Refused(_drift_text(live_only, differing, live_assets.assets,
                                  base_assets.assets))

    missing = tuple(key for key in base_assets.assets
                    if key not in live_assets.assets)
    old_lines = len(live_source.splitlines())
    if not missing:
        return Plan(live=live, base_label=base_label, old_bytes=old_bytes,
                    new_bytes=old_bytes, missing=(), insertion="", offset=0,
                    anchor_line=live_assets.node.end_lineno or 0,
                    old_lines=old_lines, new_lines=old_lines,
                    live_assets=live_assets.assets,
                    expected_assets=base_assets.assets)

    offset, anchor_line, ending = _anchor(live_assets, str(live))
    insertion = _insertion(base_assets, missing, _live_indent(live_assets),
                           ending)
    new_text = live_source[:offset] + insertion + live_source[offset:]

    # The one guarantee that matters: this is the old text with one insertion.
    if new_text[:offset] != live_source[:offset] \
            or new_text[offset + len(insertion):] != live_source[offset:]:
        raise Refused("internal check failed: the planned text is not a pure "
                      "insertion; nothing was changed")
    try:
        compile(new_text, str(live), "exec")
    except SyntaxError as exc:
        raise Refused(f"the planned insertion would not compile: {exc.msg} "
                      f"(line {exc.lineno}); nothing was changed") from None
    try:
        planned = find_static_assets(new_text, f"{live} (planned)")
    except Refused as exc:
        raise Refused(f"the planned insertion would corrupt the table: {exc}; "
                      "nothing was changed") from None
    if planned.assets != base_assets.assets:
        raise Refused("the planned insertion would not reproduce the base "
                      "whitelist; nothing was changed")
    inserted_lines = len(insertion.splitlines())
    new_lines = len(new_text.splitlines())
    if new_lines - old_lines != inserted_lines:
        raise Refused(f"internal check failed: the planned line delta is "
                      f"{new_lines - old_lines}, expected {inserted_lines}; "
                      "nothing was changed")
    return Plan(live=live, base_label=base_label, old_bytes=old_bytes,
                new_bytes=new_text.encode("utf-8"), missing=missing,
                insertion=insertion, offset=offset, anchor_line=anchor_line,
                old_lines=old_lines, new_lines=new_lines,
                live_assets=live_assets.assets,
                expected_assets=base_assets.assets)


# -------------------------------------------------------------------- write --

def _atomic_write(path: Path, data: bytes) -> None:
    """Write `data` through a temp file in the same folder and one `os.replace`."""
    mode = None
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        pass
    handle, temp_name = tempfile.mkstemp(prefix=path.name + ".tmp-",
                                         dir=str(path.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            try:
                os.chmod(temp, mode)
            except OSError:
                pass
        os.replace(temp, path)
    except BaseException:
        try:
            temp.unlink()
        except OSError:
            pass
        raise


def _make_backup(live: Path, data: bytes, stamp: str) -> Path:
    """Keep `data` in `<live>.before-<stamp>`; never overwrite a different backup.

    The collision suffix is a counter, not a clock: a date stamp is stable, two
    backups made in the same second must still be two files, and `xb` makes the
    loser of a race take the next number rather than share the winner's file.
    """
    first = live.with_name(live.name + ".before-" + stamp)
    if first.is_file() and first.read_bytes() == data:
        return first
    for attempt in range(100):
        candidate = first if attempt == 0 else live.with_name(
            f"{live.name}.before-{stamp}-{attempt}")
        try:
            with open(candidate, "xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            return candidate
        except FileExistsError:
            continue
    raise OSError(f"cannot find a free backup name beside {live}")


def _compiles_on_disk(path: Path) -> tuple:
    """(ok, detail): a fresh interpreter reads and compiles the file on disk."""
    try:
        proc = subprocess.run([sys.executable, "-B", "-c", _COMPILE_CODE,
                               str(path)],
                              capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"could not run the check: {exc}"
    if proc.returncode == 0:
        return True, ""
    detail = (proc.stderr or proc.stdout).strip().splitlines()
    return False, detail[-1] if detail else f"exit {proc.returncode}"


def _written_problems(plan: Plan) -> str:
    """What is wrong with the file just written, or "" when everything holds."""
    try:
        data = plan.live.read_bytes()
    except OSError as exc:
        return f"cannot read it back: {exc}"
    if data != plan.new_bytes:
        return "the bytes on disk are not the planned bytes"
    ok, detail = _compiles_on_disk(plan.live)
    if not ok:
        return f"a fresh interpreter could not compile it: {detail}"
    try:
        assets = find_static_assets(_decode(data, str(plan.live)),
                                    str(plan.live)).assets
    except Refused as exc:
        return str(exc)
    if assets != plan.expected_assets:
        return "the whitelist read back from disk does not equal the base's"
    return ""


def apply_plan(plan: Plan, stamp: str) -> Path:
    """Write the planned insertion, or raise `Refused` having restored the file."""
    if not plan.missing:
        raise Refused("there is nothing to insert; refusing to write")
    if plan.live.read_bytes() != plan.old_bytes:
        raise Refused("the live file changed after the plan was made (its bytes "
                      "differ); nothing was written")
    backup = _make_backup(plan.live, plan.old_bytes, stamp)
    print(f"BACKUP {backup} ({len(plan.old_bytes):,} bytes, the file before "
          "this run)")
    _atomic_write(plan.live, plan.new_bytes)
    print(f"WROTE  {plan.live} (temp file beside it, then one os.replace)")
    problems = _written_problems(plan)
    if problems:
        _atomic_write(plan.live, plan.old_bytes)
        raise Refused(f"the written file failed its read-back check ({problems}); "
                      f"the original bytes were restored and the backup is "
                      f"{backup}")
    print("CHECK  read back from disk: it compiles in a fresh interpreter and "
          "its whitelist equals the base")
    print(f"PASS   {len(plan.missing)} key(s) inserted; "
          f"{len(plan.old_bytes):,} -> {len(plan.new_bytes):,} bytes; backup "
          f"{backup.name}")
    return backup


# ------------------------------------------------------------------- verify --

def _bare_name(name) -> bool:
    """A served name is one file beside the server - never a path from a table."""
    return (isinstance(name, str) and name not in ("", ".", "..")
            and "/" not in name and "\\" not in name)


def _report_verify(folder: Path) -> int:
    """Read-only check of the face whitelist and its served files in `folder`."""
    hud = folder / "jarvis_hud.py"
    if not hud.is_file():
        raise OSError(f"{hud} is not a file")
    assets = find_static_assets(_decode(hud.read_bytes(), str(hud)),
                                str(hud)).assets
    missing_keys = [key for key in FACE_KEYS if key not in assets]
    bad_entries, missing_files = [], []
    for key in FACE_KEYS:
        entry = assets.get(key)
        if entry is None:
            continue
        name = entry[0] if isinstance(entry, (tuple, list)) and entry else None
        if not _bare_name(name):
            bad_entries.append((key, entry))
            continue
        if not (folder / name).is_file():
            missing_files.append(name)
    print(f"LIVE  {hud}")
    print(f"FACE  {len(FACE_KEYS)} key(s): the face page and the modules it "
          "loads")
    for key in missing_keys:
        print(f"MISSING KEY   {key}")
    for key, entry in bad_entries:
        print(f"BAD ENTRY     {key} -> {entry!r} (a served name must be a bare "
              "file name beside the server)")
    for name in missing_files:
        print(f"MISSING FILE  {name} (not in {folder})")
    if missing_keys or bad_entries or missing_files:
        print(f"FAIL  {len(missing_keys)} key(s) missing, {len(bad_entries)} bad "
              f"entry(s), {len(missing_files)} file(s) missing; the face page "
              "would be incomplete")
        return 1
    print("PASS  the live whitelist carries every face key and every file it "
          "names exists beside jarvis_hud.py")
    return 0


# --------------------------------------------------------------------- main --

def _print_plan(plan: Plan, apply_mode: bool) -> None:
    print(f"BASE  {plan.base_label} ({len(plan.expected_assets)} key(s))")
    print(f"LIVE  {plan.live} ({len(plan.live_assets)} key(s))")
    print(f"MATCH {len(plan.live_assets)} live key(s) are in the base with "
          "identical values (no live-only key, no differing value)")
    if not plan.missing:
        print("NOTHING TO DO  the live whitelist already carries every base key.")
        return
    print(f"ADD   {len(plan.missing)} key(s) the base has and the live file "
          "lacks:")
    for key in plan.missing:
        print(f"        {key}")
    print(f"INSERT (exact lines, before line {plan.anchor_line}, the "
          "STATIC_ASSETS closing brace):")
    for line in plan.insertion.splitlines():
        print(line)
    print(f"PLAN  +{len(plan.missing)} key(s), "
          f"{len(plan.insertion.encode('utf-8')):,} byte(s), "
          f"{len(plan.insertion.splitlines())} line(s)")
    print(f"      {len(plan.old_bytes):,} -> {len(plan.new_bytes):,} bytes; "
          f"{plan.old_lines:,} -> {plan.new_lines:,} lines")
    absent = []
    for key in plan.missing:
        entry = plan.expected_assets.get(key)
        name = entry[0] if isinstance(entry, (tuple, list)) and entry else None
        if _bare_name(name) and not (plan.live.parent / name).is_file():
            absent.append(name)
    if absent:
        print(f"WARNING  {len(absent)} inserted key(s) name a file not beside the "
              "live server yet; the whitelist alone would 404 until the shipped "
              "sync copies them")
    if not apply_mode:
        print("DRY RUN  nothing was written. Re-run with --apply to write (a "
              ".before-<date> backup is made first).")


def _refused(exc: Refused) -> int:
    print("REFUSED", file=sys.stderr)
    for line in str(exc).splitlines():
        print(f"  {line}", file=sys.stderr)
    print("Nothing was changed.", file=sys.stderr)
    return 1


def _error(exc: OSError) -> int:
    print(f"ERROR  {exc}", file=sys.stderr)
    return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Rehearse or apply the STATIC_ASSETS whitelist deploy onto "
                    "a live jarvis_hud.py, refusing drift.")
    parser.add_argument("live", nargs="?", type=Path,
                        help="path to the live jarvis_hud.py")
    parser.add_argument("--ref", default=DEFAULT_REF,
                        help=f"git ref holding the published base "
                             f"(default: {DEFAULT_REF})")
    parser.add_argument("--repo", type=Path, default=ROOT,
                        help="repository root holding jarvis-backend/ "
                             "(default: this checkout)")
    parser.add_argument("--base-file", type=Path,
                        help="read the base from this file instead of --ref "
                             "(rehearsal and tests)")
    parser.add_argument("--apply", action="store_true",
                        help="write the insertion (default is a dry run)")
    parser.add_argument("--verify-live", type=Path, metavar="FOLDER",
                        help="only check the face keys and served files in "
                             "FOLDER; never writes")
    parser.add_argument("--date", metavar="YYYY-MM-DD",
                        help="stamp for the .before-<date> backup "
                             "(default: today)")
    args = parser.parse_args(argv)

    if args.verify_live is not None:
        if args.live is not None:
            parser.error("give either a live file or --verify-live, not both")
        if args.apply:
            parser.error("--apply cannot be used with --verify-live (it never "
                         "writes)")
        try:
            return _report_verify(args.verify_live)
        except Refused as exc:
            return _refused(exc)
        except OSError as exc:
            return _error(exc)

    if args.live is None:
        parser.error("a live jarvis_hud.py path is required "
                     "(or use --verify-live FOLDER)")
    stamp = args.date or _dt.date.today().isoformat()
    if not DATE_RE.match(stamp):
        parser.error(f"--date must be YYYY-MM-DD, not {stamp!r}")

    try:
        if args.base_file is not None:
            base_source = _decode(args.base_file.read_bytes(),
                                  str(args.base_file))
            label = str(args.base_file)
        else:
            raw, label = _base_from_ref(args.ref, args.repo)
            base_source = _decode(raw, label)
        plan = make_plan(args.live, base_source, label)
    except Refused as exc:
        return _refused(exc)
    except OSError as exc:
        return _error(exc)

    _print_plan(plan, args.apply)
    if not args.apply or not plan.missing:
        return 0
    try:
        apply_plan(plan, stamp)
    except Refused as exc:
        return _refused(exc)
    except OSError as exc:
        return _error(exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
