#!/usr/bin/env python3
"""reseal_live_install.py - put a drifted live backend back on the bytes this repository
ships, and repair the installer's record rows the repository can prove.

WHY THIS EXISTS (Gemini's Q3 ruling, 2026-10-30; `main` after #997)

    The owner's live install reports **93 FAIL rows** from
    `py -3 backend\\selftest.py --preflight`: the "changed since the installer wrote
    it" rows of the installer's own record (`_jarvis-state.json`, written beside the
    backend by `scripts/apply-patches.ps1`) plus the patch rows of a stack the
    patcher can no longer replay on that folder. The reviewer's Q3 ruling says why
    the two are one problem: `backend/rebuilt/` in `main` already holds the exact,
    CI-verified post-patch result of the stack, but the live PC's base files sit at
    an older intermediate state, and the record still holds the hashes of that
    older state - so the patcher refuses, the record disagrees with the folder, and
    `tools/reconcile_live_backend.py` cannot close the gap because closing it means
    writing the installer's own record, which is not that tool's job.

    Q3 offered three routes and chose **`(b')` direct `backend/rebuilt/` parity
    re-seal on a quiet `main`**: compare the live folder against `backend/rebuilt/*`
    plus the installer's `$SHIPPED` list, copy any drifted file into place with a
    full backup, purge stale bytecode and compile the result, and repair the record
    rows so the preflight's module check agrees with the folder again.

WHY A SIBLING TOOL AND NOT A `--reseal` MODE ON THE DEPLOY TOOL

    The smaller, clearer change. `tools/reconcile_live_backend.py` is the full
    deploy: `$SHIPPED` sync, the 165-patch delta table, ready plug-ins, route probes,
    a journaled backup folder - and, by design since TOOL-1, a REF GUARD that
    refuses to run from a checkout that is not the commit `--ref` names. A reseal
    mode would have to run from the branch that carries it (a new tool cannot be
    merged and checked out at `origin/main` in the same breath), so it would either
    inherit a guard that makes it unusable exactly when it is needed, or need a
    bypass that weakens a guard added for a measured bug. And the reseal writes a
    file the deploy must never write - the installer's record - so keeping the two
    apart keeps "what the deploy owns" and "what the record owns" separate.

    The parity that matters is kept: this tool imports the deploy's own proven
    pieces rather than copying them - `parse_powershell_list` (the authoritative
    `$SHIPPED` list, with its comment and refusal rules), `flatten_shipped`
    (`rebuilt/x` -> `x` beside `jarvis_hud.py`, refused on `..`, absolute paths and
    duplicates), `plan_shipped` (the byte comparison), `git_show` (the exact blob at
    a commit, no checkout), `git_rev_parse`, `purge_pycache` and the shared
    `Refused` - so the two tools cannot disagree about which files are shipped, or
    where they land.

WHAT IT DOES, AND IN WHAT ORDER

    1. PLAN (always; the run is read-only up to the first backup).
       `$SHIPPED` is read from `--ref` (`git show <ref>:scripts/apply-patches.ps1`),
       never the working tree, and every module's BYTES come from that same commit
       (`git show <ref>:backend/<path>`) - the same rule as the deploy, so a stale
       checkout cannot plan an older file. Each entry is compared with the live
       folder BY BYTES: `update` (differs), `add` (absent) or `unchanged`.
    2. REHEARSE. Every Python file that would be written is `py_compile`d in a
       temporary folder first. A file that does not compile stops the run before
       anything is touched.
    3. THE RECORD. `_jarvis-state.json` is read and every row is judged against the
       bytes the folder WILL hold after step 1:
         * `current`    - the recorded hash will be the hash of the folder's bytes;
         * `rehash`     - the repository ships this file and its bytes hash
                          differently from the row, so the row is re-written with the
                          repository's own hash. This is the class the tool OWNS: the
                          new number is not a guess, it is `sha256` of a blob in the
                          commit being deployed;
         * `unprovable` - there is a row, its hash no longer matches, and this
                          repository does not ship the file (the five patched base
                          files - see `PATCHED_FILES` in the deploy tool). No copy in
                          this repository is those bytes, so the tool REFUSES to
                          invent a hash and lists every such row with both numbers;
         * `absent-unprovable` - a row for a file that is not in the folder and not
                          shipped, so it cannot even be restored; listed, never
                          invented.
       `--rebaseline-unprovable` (OFF by default) records the CURRENT bytes of the
       unprovable rows, which is what `apply-patches.ps1` does on a run with no
       usable record: "take the owner's current files as the starting baseline
       (hashes only; nothing of his is modified) and then name whatever it could not
       tie to a patch". It is the only way to a record that agrees with a folder the
       patcher cannot reproduce - and it is the owner's decision, so it is a flag and
       every row it re-records is printed with both hashes.
    4. PROJECT THE PREFLIGHT (read-only). `backend/selftest.py`'s own
       `patch_states()` is called twice - against the folder as it is, and against
       the folder as it WOULD be, through that function's own `read` seam - so the
       report says how many patches read `not applied`/`partly` now and after. The
       module rows are counted with the same four rules `pf_modules` uses (a FAIL is
       a row whose hash no longer matches its file, a row whose file is gone, or a
       shipped file that is not in the folder), and the dry run also prints what the
       real check says about the folder now, so the two numbers can be compared. The
       rest of the run does not depend on `backend/selftest.py` importing: if it
       cannot, that section says so.
    5. APPLY (`--apply` only, and the only place anything is written).
         a. every file to be replaced is copied to `<name>.before-reseal-<stamp>`
            beside it, and every file to be added is remembered so a failure removes
            it again - the copy happens BEFORE the write, never after;
         b. the repository's bytes are written exactly (`write_bytes`, no line-ending
            rewriting, no re-encoding);
         c. every written `.py` is compiled FROM THE LIVE FOLDER, with its bytecode
            sent to a temporary file so no `.pyc` is left behind - "the result
            compiles", not "the plan compiled";
         d. stale `__pycache__/*.pyc` are purged (the `jarvis_speech` trap);
         e. the same comparison as step 1 is run again and must be clean. If any
            write or compile fails, every file this run wrote is restored from its
            backup (and every file it created is removed) before the run reports;
         f. the record is written LAST, atomically (temporary file, then replace),
            with only the `rehash` rows (and the `--rebaseline-unprovable` rows)
            changed. Every other row, `patchList`, `patches`, `written` and every
            other key are kept exactly as they were, and a `resealed` key is added
            recording this tool, the commit and which rows it wrote - so the record
            says how it got there instead of pretending the installer wrote these
            numbers;
         g. the record is read back and the changed rows are checked, then steps 1
            and 3 are re-planned and printed again as the convergence proof.
    A second `--apply` on an already-current folder writes NOTHING at all - no
    backup, no compile, no record rewrite - and says so.

WHAT IT DOES NOT DO - the honest limits

    * It never invents a file or a hash. Every byte it writes comes from the commit
      `--ref` names; every hash it writes is the hash of one of those blobs.
    * It cannot repair a PATCH. It carries the ten `rebuilt/*` modules and every
      other file the installer ships whole; a patch that writes a file the
      repository does not ship (the five base files) is outside it. `jarvis_hud.py`
      and `jarvis_gate.py` in particular are repaired today by
      `tools/repair_live_backend_gaps.py` (the 2026-10-30 `(a)` ruling, #997), and
      the rows that stay red after a reseal are exactly those files'.
    * It cannot run `scripts/apply-patches.ps1`. When the patcher can run again, IT
      is still the only thing that may re-record the patch-owned files (and the
      non-Python beside-files); a reseal is a bridge, not the destination. The record
      it writes is one the patcher reads and overwrites on its next finished run,
      which is correct.
    * It never copies `jarvis-backend/*` over live. That folder is the published
      base, a snapshot of an older live folder with the stack already in it; writing
      it over the live files would move them BACKWARDS (the deploy tool refuses it
      for the same measured reason).
    * It never restarts Jarvis and never probes a route. After `--apply`, restart
      Jarvis yourself and read the start-up banner. A run that is killed part-way
      leaves every file it had reached backed up beside itself
      (`<name>.before-reseal-<stamp>`) and the record untouched, so re-running
      `--apply` finishes the job; restoring by hand is the same copy back.
    * It does not touch the phone, the running server, or any file outside the
      folder `--backend-path` names (plus its own `<name>.before-reseal-<stamp>`
      siblings and the record beside it).
    * The hash fold is `sha256` of the bytes with CRLF folded to LF - the rule
      `backend/selftest.py`'s `_sha` and `scripts/apply-patches.ps1`'s
      `Get-Sha256Hex -AsLf` both use for a UTF-8 file. A file carrying a UTF-8
      byte-order mark would hash differently in the two (PowerShell's text read
      drops the mark, the byte read keeps it); no `.py` in this repository has one,
      and this paragraph says so rather than pretending the two rules are identical.

USAGE

    py -3 tools/reseal_live_install.py --backend-path "<live backend>"              # dry run
    py -3 tools/reseal_live_install.py --backend-path "<live backend>" --apply      # after review
    py -3 tools/reseal_live_install.py --backend-path "<live backend>" --apply --rebaseline-unprovable

    Run it from the checkout that carries it (this branch, until it is merged) and
    let the bytes come from the commit being deployed: the default `--ref` is
    `origin/main`. `--ref <commit>` chooses another commit. The dry run writes
    nothing; the second `--apply` is a no-op.

EXIT CODES

    0  the plan is clean (dry run), or `--apply` converged and every record row it
       can own now agrees with the folder
    1  the folder is repaired but rows remain this tool will not invent - it names
       every one, and the preflight's module check keeps reporting them until the
       patcher runs again (or `--rebaseline-unprovable` is asked for, deliberately)
    2  refused before writing (bad arguments, an empty or unknown `--ref`, a folder
       that is not a backend, a shipped entry that is not a safe relative path, a
       row that names a path outside the folder, a rehearsal or a compile failure) -
       nothing was written, or everything written was rolled back
"""
from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import shutil
import sys
import tempfile
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

#: The deploy tool's own proven parsers and git readers are imported, never copied:
#: `$SHIPPED` parsing, the `rebuilt/x -> x` flatten rule, the byte comparison,
#: `git show <ref>:<path>`, the shared `Refused`, and the `.pyc` purge all behave
#: exactly as the deploy does.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import reconcile_live_backend as deploy  # noqa: E402

#: One exception type for both tools, so a caller catching `Refused` catches both.
Refused = deploy.Refused

#: The suffix every replaced file is kept under, beside itself (the repair tool's
#: `.before-repair-<stamp>` convention, one word different so the two are never
#: mistaken for each other in a backup listing).
BACKUP_SUFFIX = ".before-reseal-"

#: The installer's record, beside the backend. `backend/selftest.py` calls it
#: `INSTALL_RECORD` and `scripts/apply-patches.ps1` writes it at `-Manifest`'s
#: default; both are named here so a reader can check the three agree.
MANIFEST_NAME = "_jarvis-state.json"

#: The only record format this tool will edit. An unknown schema is refused rather
#: than rewritten in a shape its owner does not know.
MANIFEST_SCHEMA = "jarvis-updater-manifest/1"

#: Written into the record so it says how its numbers got there. `apply-patches.ps1`
#: ignores unknown keys and drops this one on its next finished run, which is right:
#: its own run then re-records everything it can prove.
RESEALED_KEY = "resealed"


def folded_sha256(data: bytes) -> str:
    """The hash the installer's record holds: `sha256` of the bytes, CRLF folded to LF.

    `backend/selftest.py`'s `_sha` and `scripts/apply-patches.ps1`'s
    `Get-Sha256Hex -AsLf` both fold the line ending before hashing - the record is
    about the text, not about how this PC happened to save it - so this tool uses the
    same fold for the numbers it compares and writes. See the module docstring's
    limits for the one case (a byte-order mark) where the two implementations can
    disagree.
    """
    return hashlib.sha256(bytes(data).replace(b"\r\n", b"\n")).hexdigest()


def _summ(out: Callable, label: str, items: Iterable, limit: int = 12) -> None:
    """The deploy tool's summary shape: a count, then names, then how many are hidden."""
    names = list(items)
    if not names:
        return
    shown = ", ".join(str(n) for n in names[:limit])
    out(f"  {label}: {len(names)}" + (f": {shown}" if len(names) <= limit
                                     else f" (first {limit}): {shown}"))
    if len(names) > limit:
        out(f"      ... and {len(names) - limit} more")


def _stuck_lines(stuck: Iterable) -> list:
    """One line per target file, EVERY patch named - nothing summarised away.

    The patch rows are the half of the preflight a reseal cannot move, so they are the
    list someone has to act on: a "... and 177 more" there would hide the answer. The
    rows are grouped by file because that is the unit the patcher works on, and each
    patch carries its own state and line count so a partly-applied one is visible.
    """
    groups: dict = {}
    for name, target, state, present, total in stuck:
        groups.setdefault(target, []).append(f"{name} ({state} {present}/{total})")
    return [f"      {target} ({len(names)}): " + ", ".join(sorted(names))
            for target, names in sorted(groups.items())]


def _safe_target(live: Path, rel: str) -> Path:
    """`live / rel`, refused unless it really is one file directly inside `live`.

    A record row is data from a file a previous run wrote, so it is checked like
    untrusted input: no absolute path, no drive, no `..`, and the resolved parent
    must be the live folder itself (every shipped file lands beside `jarvis_hud.py`,
    so a row naming a subfolder is a row this tool does not understand and says so).
    """
    posix = str(rel).replace("\\", "/")
    if not posix or posix.startswith("/") or ":" in posix or ".." in posix.split("/"):
        raise Refused(f"the installer's record names {rel!r}, which is not a safe "
                      f"relative file name; the record was not changed")
    target = Path(live) / posix
    if target.parent.resolve() != Path(live).resolve():
        raise Refused(f"the installer's record names {rel!r}, which is not a file "
                      f"directly in {live}; this tool only knows the layout the "
                      f"installer writes, so it left the record alone")
    return target


@dataclass
class FilePlan:
    """One `$SHIPPED` entry: what the repository holds, and what the folder holds."""

    live_name: str              # e.g. "jarvis_compute.py"
    repo_path: str              # e.g. "rebuilt/jarvis_compute.py"
    status: str                 # "update" | "add" | "unchanged"
    blob: bytes                 # the repository's exact bytes at --ref
    live_bytes: Optional[bytes] = None
    repo_sha: str = ""          # folded_sha256(blob)
    live_sha: str = ""          # folded_sha256(live bytes), "" when absent

    @property
    def changes(self) -> bool:
        return self.status != "unchanged"


@dataclass
class RowPlan:
    """One row of `_jarvis-state.json`'s `files`, judged against the folder's FUTURE bytes.

    `got_now` and `got_after` are two different facts on purpose: the first is what
    the preflight is complaining about today, the second is what this run is
    responsible for. `exists_now` is separate from `got_now` because an absent file
    and a file with the wrong bytes are both a FAIL, but only one of them can be
    compared.
    """

    rel: str
    want: str                   # the hash the record holds ("" when it records none)
    got_now: str                # the hash of the file in the folder now ("" = absent)
    got_after: str              # the hash the folder will hold when this run is done
    exists_now: bool
    shipped: bool               # the repository ships this file (so it can prove bytes)
    state: str                  # current | rehash | unprovable | absent-unprovable

    @property
    def failing_now(self) -> bool:
        """Would the preflight's modules check call this row a FAIL right now?

        Mirrors `pf_modules`: a file that is not there is a FAIL whatever the record
        says, and a row whose hash does not match is a FAIL - but a row carrying no
        hash at all is the "the record does not speak for it" WARN, not a FAIL.
        """
        return (not self.exists_now) or (self.want != "" and self.got_now != self.want)


@dataclass
class Plan:
    files: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    no_row: list = field(default_factory=list)
    record: Optional[dict] = None
    rehearsal: list = field(default_factory=list)


# ---------------------------------------------------------------------------
#   Step 1 - the file plan (byte-exact, from --ref)
# ---------------------------------------------------------------------------

def _cached_show(show: Callable) -> Callable:
    """One blob read per repository path per run.

    A reseal reads the same 295 blobs twice - once to plan, once to prove the write
    landed - and on Windows each `git show` is its own process (about 0.12 s here, so
    the second pass alone costs half a minute). The commit cannot change under one
    run, so the second read is the same bytes; caching them removes the cost without
    changing a single decision. The LIVE files are re-read every time, which is the
    half that must be fresh.
    """
    cache: dict = {}

    def cached(repo, ref, path):
        key = (str(repo), str(ref), str(path))
        if key not in cache:
            cache[key] = show(repo, ref, path)
        return cache[key]

    return cached


def plan_files(repo: Path, ref: str, live: Path, shipped: Iterable[str],
               show: Optional[Callable] = None) -> list:
    """[(FilePlan)] for every `$SHIPPED` entry, compared with the live folder BY BYTES.

    The comparison and the flatten rule are the deploy tool's own (`plan_shipped`
    over `flatten_shipped`), deliberately: a file the deploy calls unchanged must be
    a file this tool calls unchanged, or the two would fight over the same folder.

    `show` is one seam for THIS tool - a `show(repo, ref, repository_path)` returning
    the bytes at that path (e.g. `backend/rebuilt/jarvis_compute.py`) - and it is
    adapted to the deploy's `plan_shipped`, whose seam is the backend-relative one.
    The two shapes exist because the deploy reads its patch list (`$SHIPPED`) and its
    modules at different levels; tests should have to make one fixture, not two.
    """
    backend_show = None
    if show is not None:
        def backend_show(repo, ref, repo_path):        # the deploy's seam shape
            return show(repo, ref, f"backend/{repo_path}")
    actions = deploy.plan_shipped(Path(repo), ref, Path(live), list(shipped),
                                  show=backend_show)
    plans = []
    for action in actions:
        target = Path(live) / action.live_name
        if target.exists() and not target.is_file():
            raise Refused(f"{target} is not a regular file, so {action.repo_path} cannot "
                          f"be put there; nothing was written")
        live_bytes = target.read_bytes() if target.is_file() else None
        plans.append(FilePlan(
            live_name=action.live_name,
            repo_path=action.repo_path,
            status=action.status,
            blob=action.blob or b"",
            live_bytes=live_bytes,
            repo_sha=folded_sha256(action.blob or b""),
            live_sha=folded_sha256(live_bytes) if live_bytes is not None else "",
        ))
    return plans


def rehearse(files: Iterable[FilePlan]) -> list:
    """`py_compile` every Python file the run would write. Returns plain error sentences.

    Compiled in a temporary folder from the exact bytes, never from the live folder:
    a rehearsal must not be able to change what it is checking. The only write is
    under the system temporary folder; the live folder, the record and the checkout
    are untouched.
    """
    errors = []
    tmp = Path(tempfile.mkdtemp(prefix="reseal-rehearsal-"))
    try:
        for item in files:
            if not item.changes or not item.live_name.endswith(".py"):
                continue
            path = tmp / item.live_name
            path.write_bytes(item.blob)
            try:
                # A SyntaxWarning is not a compile failure, and one file's warning in
                # the middle of a deploy report reads like this run has a problem. The
                # question asked here is only "does it compile".
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as exc:
                errors.append(f"{item.live_name}: {exc.msg}")
            except Exception as exc:                          # noqa: BLE001
                errors.append(f"{item.live_name}: {type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return errors


# ---------------------------------------------------------------------------
#   Step 3 - the installer's record
# ---------------------------------------------------------------------------

def read_record(live: Path) -> tuple:
    """(the record, why it cannot be used). Exactly one of the two is set.

    The reasons are sentences for a person, in the same shape
    `backend/selftest.py`'s `_install_record` uses, because they are read in the same
    place: beside the backend, by someone deciding what to do next.
    """
    path = Path(live) / MANIFEST_NAME
    if not path.is_file():
        return None, (f"there is no {MANIFEST_NAME} beside the backend yet, so there are "
                      f"no rows to repair (the file checks still run)")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:                                  # noqa: BLE001
        return None, (f"{MANIFEST_NAME} cannot be read ({type(exc).__name__}), so no row "
                      f"in it was changed")
    if not isinstance(doc, dict):
        return None, f"{MANIFEST_NAME} is not a JSON object, so no row in it was changed"
    if str(doc.get("schema") or "") != MANIFEST_SCHEMA:
        return None, (f"{MANIFEST_NAME} says schema {doc.get('schema')!r}, not "
                      f"{MANIFEST_SCHEMA!r}; this tool only edits the format it knows, "
                      f"so no row in it was changed")
    if not isinstance(doc.get("files"), dict) or not doc["files"]:
        return None, (f"{MANIFEST_NAME} names no files, so there is nothing to repair "
                      f"(the preflight reports that as a warning, not a failure)")
    odd = sorted(rel for rel, row in doc["files"].items() if not isinstance(row, dict))
    if odd:
        return None, (f"{MANIFEST_NAME} has {len(odd)} row(s) that are not objects "
                      f"({', '.join(odd[:4])}), which no run of the installer writes; this "
                      f"tool does not know what such a row means, so no row in it was "
                      f"changed")
    return doc, ""


def plan_rows(live: Path, record: Optional[dict], files: Iterable[FilePlan]) -> tuple:
    """([(RowPlan)], [shipped names the record does not speak for]).

    A row is judged against the bytes the folder will hold AFTER the file step: for a
    shipped file that is the repository's bytes, whichever way the file step goes.
    """
    items = {item.live_name: item for item in files}
    if not record:
        return [], sorted(items)
    rows = []
    for rel in sorted(record.get("files") or {}):
        entry = record["files"][rel] if isinstance(record["files"][rel], dict) else {}
        want = str(entry.get("sha256") or "")
        target = _safe_target(Path(live), rel)
        item = items.get(rel)
        exists_now = target.is_file()
        got_now = folded_sha256(target.read_bytes()) if exists_now else ""
        if item is not None:
            got_after, shipped = item.repo_sha, True
        else:
            got_after, shipped = got_now, False
        if shipped:
            state = "rehash" if got_after != want else "current"
        elif not exists_now:
            state = "absent-unprovable"
        elif got_now != want:
            state = "unprovable"
        else:
            state = "current"
        rows.append(RowPlan(rel=rel, want=want, got_now=got_now, got_after=got_after,
                            exists_now=exists_now, shipped=shipped, state=state))
    spoken = {row.rel for row in rows}
    # Only `.py`: `backend/selftest.py` judges a shipped file that is not Python by
    # whether it is there at all and NEVER reports it as unrecorded (the record holds
    # *.py), so counting the 52 `.js`/`.css`/font files here would print a warning the
    # preflight does not make.
    no_row = sorted(name for name in items if name not in spoken and name.endswith(".py"))
    return rows, no_row


# ---------------------------------------------------------------------------
#   Step 4 - the preflight projection (read-only, and optional)
# ---------------------------------------------------------------------------

def _selftest(repo: Path) -> tuple:
    """(the preflight module, why not). Never fatal: the plan does not depend on it.

    Imported only when the checkout this run names really has `backend/selftest.py`.
    That check is not politeness: a fixture repository has no such file, and without
    it a `selftest` already on `sys.path` from somewhere else would be imported and
    asked about the wrong folder - a projection that silently describes a different
    tree. A path, not a name, decides.
    """
    module = Path(repo) / "backend" / "selftest.py"
    if not module.is_file():
        return None, f"there is no backend/selftest.py under {repo}"
    try:
        backend_dir = str(module.parent)
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        import selftest                                     # noqa: PLC0415
        return selftest, ""
    except Exception as exc:                                  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def project_patches(live: Path, files: Iterable[FilePlan], states_fn: Callable) -> dict:
    """How the preflight's patch rows move, using `selftest.patch_states` itself.

    `states_fn(backend, read)` is the seam: the real one calls
    `backend/selftest.py`'s `patch_states`, and a test supplies its own. `read` is
    that function's OWN seam for "what does this file say" - so the "after" list is
    produced by the same rules, over the repository's bytes for the files this run
    would write and over the folder's current bytes for everything else. Nothing is
    guessed at and nothing is written.
    """
    replaced = {item.live_name: item.blob for item in files if item.changes}

    def projected(name: str) -> str:
        blob = replaced.get(name)
        if blob is not None:
            return blob.decode("utf-8", "replace")
        return (Path(live) / name).read_text(encoding="utf-8", errors="replace")

    try:
        before = states_fn(Path(live), None)
        after = states_fn(Path(live), projected)
    except Exception as exc:                                  # noqa: BLE001
        return {"why": f"{type(exc).__name__}: {exc}"}
    flips = []
    stuck = []
    after_by = {(n, f): (s, p, t) for n, f, s, p, t in after}
    for name, target, state, present, total in before:
        then, after_present, after_total = after_by.get((name, target),
                                                        (state, present, total))
        if state in ("not applied", "partly") and then == "applied":
            flips.append((name, target))
        if then in ("not applied", "partly"):
            stuck.append((name, target, then, after_present, after_total))
    return {"before": before, "after": after, "flips": flips, "stuck": sorted(stuck)}


def module_rows(rows: Iterable[RowPlan], files: Iterable[FilePlan], *,
                record_written: bool) -> tuple:
    """(FAIL rows now, FAIL rows after) for the preflight's modules check.

    The four row kinds `backend/selftest.py`'s `pf_modules` emits are mirrored here
    rather than imported: the plan must not depend on a module that cannot be
    imported from a working checkout, and the rule is one sentence - a FAIL is a row
    whose hash no longer matches its file, a row whose file is gone, or a shipped file
    that is not in the folder. A file the record does not speak for is a WARN there
    and is not counted here. The dry run also prints what the real check says about
    the folder now, so the two numbers are never quietly different.
    """
    rows = list(rows)
    absent_shipped = {item.live_name: item for item in files if item.live_bytes is None}
    recorded = {row.rel for row in rows}
    now = sum(1 for row in rows if row.failing_now)
    now += sum(1 for name in absent_shipped if name not in recorded)
    if record_written:
        # Every shipped row is re-hashed to the repository's own bytes, so the only
        # rows left disagreeing are the ones this repository cannot prove.
        after = sum(1 for row in rows if not row.shipped and row.failing_now)
    else:
        # No record edit: a shipped row still fails while its recorded hash is not the
        # repository's, and a row this repository does not ship keeps the file it has.
        after = sum(1 for row in rows if row.shipped and row.got_after != row.want)
        after += sum(1 for row in rows if not row.shipped and row.failing_now)
    return now, after


# ---------------------------------------------------------------------------
#   Step 5 - writing
# ---------------------------------------------------------------------------

def backup_name(target: Path, stamp: str) -> Path:
    return Path(target).with_name(Path(target).name + BACKUP_SUFFIX + stamp)


def write_files(files: Iterable[FilePlan], live: Path, stamp: str,
                out: Callable) -> tuple:
    """Write the add/update bytes, each after its backup. Returns (written, backups, new).

    A failure restores every file this run wrote and removes every file it created, so
    the folder is never left half resealed: the bytes came from one commit, and half
    of them is a state neither the repository nor the record describes.
    """
    written, backups, created = [], {}, []
    try:
        for item in files:
            if not item.changes:
                continue
            target = Path(live) / item.live_name
            if target.is_file():
                keep = backup_name(target, stamp)
                shutil.copy2(target, keep)
                backups[item.live_name] = keep
            else:
                created.append(target)
            target.write_bytes(item.blob)
            written.append(item.live_name)
    except OSError as exc:
        restored = restore_written(live, backups, created, out)
        raise Refused(f"writing {written[-1] if written else 'a file'} failed ({exc}); "
                      f"{restored} file(s) were put back from their backup") from exc
    return written, backups, created


def restore_written(live: Path, backups: dict, created: Iterable[Path],
                    out: Callable) -> int:
    """Put back what `write_files` replaced and remove what it created. Never raises."""
    restored = 0
    for rel, keep in backups.items():
        try:
            shutil.copy2(keep, Path(live) / rel)
            restored += 1
        except OSError as exc:                                # noqa: BLE001
            out(f"FAIL  could not restore {rel} from {keep}: {exc}")
    for target in created:
        try:
            Path(target).unlink(missing_ok=True)
        except OSError as exc:                                # noqa: BLE001
            out(f"FAIL  could not remove the file this run created, {target}: {exc}")
    return restored


def compile_written(live: Path, names: Iterable[str]) -> list:
    """`py_compile` the files IN THE FOLDER, bytecode to a temporary file.

    Compiled from the live folder on purpose: the claim a reseal makes is "the file
    that is there now compiles", not "the bytes we meant to write compile" (the
    rehearsal already said that). The bytecode goes to a temporary folder, so no fresh
    `.pyc` is left for the purge below to miss.
    """
    errors = []
    tmp = Path(tempfile.mkdtemp(prefix="reseal-compile-"))
    try:
        for name in names:
            if not str(name).endswith(".py"):
                continue
            try:
                with warnings.catch_warnings():        # see `rehearse` for why
                    warnings.simplefilter("ignore")
                    py_compile.compile(str(Path(live) / name),
                                       cfile=str(tmp / f"{name}c"), doraise=True)
            except py_compile.PyCompileError as exc:
                errors.append(f"{name}: {exc.msg}")
            except Exception as exc:                          # noqa: BLE001
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return errors


def write_record(live: Path, record: dict, rehash: Iterable[RowPlan],
                 rebaseline: Iterable[RowPlan], *, stamp: str, ref: str,
                 ref_sha: str, out: Callable) -> list:
    """Re-write ONLY the rows this tool owns, atomically, and prove the write landed.

    Everything the installer wrote stays exactly as it was (`written`, `patches`,
    `patchList`, every untouched row); a re-hashed row gets the repository's own hash,
    a re-baselined row gets the folder's own hash (only when explicitly asked for),
    and a `resealed` key records this tool, the commit and the row names so the record
    says how its numbers got there.
    """
    path = Path(live) / MANIFEST_NAME
    known = record.get("files") or {}
    wanted = [(row, row.got_after) for row in rehash if row.rel in known]
    wanted += [(row, row.got_now) for row in rebaseline if row.rel in known and row.got_now]
    if not wanted:
        return []
    doc = json.loads(json.dumps(record))          # a deep copy: the caller's is untouched
    files = doc.get("files") or {}
    for row, sha in wanted:
        files[row.rel]["sha256"] = sha
    touched = [row.rel for row, _sha in wanted]
    doc[RESEALED_KEY] = {
        "tool": "tools/reseal_live_install.py",
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ref": ref,
        "commit": ref_sha,
        "rows": sorted(touched),
    }
    keep = backup_name(path, stamp)
    shutil.copy2(path, keep)
    out(f"RECORD  : backed up to {keep.name}")
    body = json.dumps(doc, indent=2, ensure_ascii=True) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    try:
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    # Prove it: the numbers this run wrote must be the numbers now on disk.
    back = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    for rel, want in ((row.rel, sha) for row, sha in wanted):
        got = str((back.get("files") or {}).get(rel, {}).get("sha256") or "")
        if got != want:
            problems.append(f"{rel}: wrote {want[:8]} but the file says {got[:8]}")
    if problems:
        raise Refused("the record was written but does not read back as written: "
                      + "; ".join(problems))
    return touched


# ---------------------------------------------------------------------------
#   The run
# ---------------------------------------------------------------------------

def run_reseal(repo: Path, live: Path, *, apply: bool = False, ref: str = "origin/main",
               rebaseline_unprovable: bool = False, show: Optional[Callable] = None,
               out: Optional[Callable] = None, stamp: Optional[str] = None,
               states_fn: Optional[Callable] = None) -> int:
    """The whole tool. Returns the exit code the CLI returns; writes only under --apply."""
    out = out or print
    repo = Path(repo).resolve()
    live = Path(live).resolve()
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    out(f"Jarvis live-install reseal - {'APPLY' if apply else 'DRY RUN'}")
    out(f"  repo: {repo}")
    out(f"  live: {live}")
    out(f"  ref : {ref}")
    if not live.is_dir():
        raise Refused(f"{live} is not a folder")
    if not (live / "jarvis_hud.py").is_file():
        raise Refused(f"no jarvis_hud.py in {live} - is this the live backend folder? "
                      f"(this tool writes only that folder and the record beside it)")
    if live == repo or repo in live.parents:
        raise Refused(f"{live} is inside this repository checkout; the live backend "
                      f"lives outside it, and this tool will not write into a checkout")
    if not (repo / "scripts" / "apply-patches.ps1").is_file():
        raise Refused(f"no scripts/apply-patches.ps1 under {repo}")
    if not str(ref or "").strip():
        raise Refused("--ref must not be empty: an empty ref would read the file list "
                      "from this checkout and the bytes from the git index")

    # The ref's own SHA is printed and recorded in the `resealed` key, but it is not
    # what decides anything: every byte comes from `git show <ref>:...` below, and a ref
    # this checkout cannot resolve fails there with git's own words. A fixture with no
    # object store (the tests' seam) therefore needs no git at all.
    try:
        ref_sha = deploy.git_rev_parse(repo, f"{ref}^{{commit}}")
    except Refused:
        ref_sha = ""
    try:
        head_sha = deploy.git_rev_parse(repo, "HEAD")
    except Refused:
        head_sha = ""
    if ref_sha:
        out(f"  bytes from {ref} = {ref_sha}")
    else:
        out(f"  bytes from {ref} (the commit is not in this checkout's git; the blob "
            f"reads below are what must succeed)")
    if head_sha and head_sha != ref_sha:
        out(f"  NOTE: this checkout's HEAD is {head_sha}, not the commit being deployed; "
            f"that is allowed here because every byte comes from {ref} and only the "
            f"patch TEXT the projection reads comes from this checkout")
    out("")

    # 1. The file plan, byte-exact, from the ref. Every blob is read at the
    #    repository-path level (`git show <ref>:backend/...`), cached for the run, so
    #    the same bytes are read once and the second comparison below costs nothing.
    show = _cached_show(show or deploy.git_show_path)
    shipped, _patches = deploy.read_patch_lists(repo, ref, show=show)
    plan = Plan()
    plan.files = plan_files(repo, ref, live, shipped, show=show)
    updates = [f for f in plan.files if f.status == "update"]
    adds = [f for f in plan.files if f.status == "add"]
    same = [f for f in plan.files if f.status == "unchanged"]
    rebuilt = sum(1 for f in plan.files if f.repo_path.startswith("rebuilt/"))
    out(f"FILES ({len(plan.files)} entries in $SHIPPED, flattened to their live names; "
        f"{rebuilt} of them are the rebuilt/ modules):")
    _summ(out, "differs (the repository's bytes will replace them)",
          sorted(f.live_name for f in updates), limit=40)
    _summ(out, "absent (the repository ships them; nothing is there)",
          sorted(f.live_name for f in adds), limit=40)
    out(f"  unchanged: {len(same)}")

    # 2. Rehearse every Python file the run would write - before anything is touched.
    plan.rehearsal = rehearse(plan.files)
    if plan.rehearsal:
        out("")
        out("REHEARSAL FAILED - nothing has been written:")
        _summ(out, "errors", plan.rehearsal, limit=20)
        raise Refused("a file this run would write does not compile, so nothing was "
                      "written; the repository's copy of that file is wrong and the "
                      "commit it comes from should be looked at")
    python_writes = sum(1 for f in plan.files if f.changes and f.live_name.endswith(".py"))
    if python_writes:
        out(f"  rehearsal: py_compile OK for {python_writes} Python file(s), in a "
            f"temporary folder (the live folder is untouched)")

    # 3. The installer's record.
    record, why = read_record(live)
    plan.record = record
    rows, no_row = plan_rows(live, record, plan.files)
    plan.rows, plan.no_row = rows, no_row
    rehash = [r for r in rows if r.state == "rehash"]
    unprovable = [r for r in rows if r.state == "unprovable"]
    absent_unprovable = [r for r in rows if r.state == "absent-unprovable"]
    current = [r for r in rows if r.state == "current"]
    mismatched_now = [r for r in rows if r.failing_now]
    have_rows = bool(record)
    out("")
    out(f"MANIFEST ({MANIFEST_NAME}):")
    if not have_rows:
        out(f"  {why}")
    else:
        written_when = str(record.get("written") or "")
        out(f"  recorded: {len(rows)} row(s)" + (f", written {written_when}"
                                                 if written_when else ""))
        out(f"  no longer matching the folder: {len(mismatched_now)}")
        out(f"  current: {len(current)}")
        _summ(out, "to re-hash (the repository proves those bytes)",
              [r.rel for r in rehash], limit=40)
        if unprovable or absent_unprovable:
            out(f"  unprovable ({len(unprovable) + len(absent_unprovable)}) - this "
                f"repository does not ship these files, so their bytes cannot be "
                f"proved here. They are NOT re-hashed unless you ask:")
            for row in unprovable + absent_unprovable:
                out(f"      {row.rel}: record {row.want[:12] or '(none)'}, folder "
                    f"{row.got_now[:12] or '(absent)'}")
            out("      The patch stack (scripts/apply-patches.ps1) is the only thing "
                "that may re-record a file it produces. --rebaseline-unprovable "
                "records the folder's own bytes for exactly these rows instead, which "
                "is what the patcher does when it has no usable record.")
        if no_row:
            _summ(out, "shipped files the record does not speak for (the preflight "
                       "calls these a warning, not a failure)", no_row, limit=12)

    # 4. The preflight projection: patches through selftest's own function, modules
    #    through the rules pf_modules uses. Read-only and never fatal.
    out("")
    out("PREFLIGHT PROJECTION (read-only):")
    before_fail, after_fail = module_rows(rows, plan.files, record_written=have_rows)
    if not have_rows:
        out("  modules : not comparable (no usable record); the preflight reports that "
            "as a warning, not a failure")
    else:
        out(f"  modules : {before_fail} failing row(s) now, {after_fail} after the "
            f"reseal")
    st, why_st = _selftest(repo)
    fn = states_fn
    patch_stuck = []
    if fn is None and st is not None:
        def fn(backend, read=None):                    # selftest's own list, its own seam
            return st.patch_states(Path(backend), read=read)
    if fn is None:
        out(f"  patches : projection unavailable ({why_st})")
    else:
        patch_proj = project_patches(live, plan.files, fn)
        if patch_proj.get("why"):
            out(f"  patches : projection unavailable ({patch_proj['why']})")
        else:
            bad_now = [s for s in patch_proj["before"] if s[2] in ("not applied", "partly")]
            bad_after = patch_proj["stuck"]
            patch_stuck = bad_after
            out(f"  patches : {len(bad_now)} not applied/partly now, "
                f"{len(bad_after)} after (of {len(patch_proj['before'])} patch/file "
                f"row(s))")
            if patch_proj["flips"]:
                _summ(out, "flip to applied",
                      [f"{n} -> {f}" for n, f in patch_proj["flips"]], limit=20)
            if bad_after:
                out(f"  still not applied/partly after the reseal "
                    f"({len(bad_after)}, by the file each patch writes):")
                for line in _stuck_lines(bad_after):
                    out(line)
    if st is not None:
        try:
            rows_now = st.pf_modules(st.Live(backend=live))
            fails_now = sum(1 for r in rows_now if r[0] == st.FAIL)
            out(f"  selftest: its own modules check reports {fails_now} FAIL row(s) on "
                f"this folder now")
            if have_rows and fails_now != before_fail:
                out(f"            NOTE: this tool's mirror of that check counted "
                    f"{before_fail}; the two disagree, so read the selftest output "
                    f"before trusting the projection")
        except Exception as exc:                              # noqa: BLE001
            out(f"  selftest: its own modules check could not be run here "
                f"({type(exc).__name__}: {exc})")

    # 5. What would be written.
    writes = [f for f in plan.files if f.changes]
    rebaseline = [r for r in unprovable if rebaseline_unprovable]
    left_alone = len(unprovable) + len(absent_unprovable) - len(rebaseline)
    out("")
    out(f"PLAN: {len(writes)} file(s) to write, {len(rehash)} record row(s) to re-hash, "
        f"{len(rebaseline)} row(s) to re-baseline, {left_alone} row(s) left as they are")
    if not apply:
        out("DRY RUN - nothing was written: no file in the live folder, no backup, no "
            "record change.")
        if writes or rehash or rebaseline:
            out("Review the list above, then add --apply. Restart Jarvis after it and "
                "read the start-up banner; this tool never restarts it.")
        return 1 if (unprovable or absent_unprovable) else 0

    # 6. APPLY. Everything above was read-only; this is the only writing part.
    if not writes and not rehash and not rebaseline:
        out("RESULT: PASS - nothing to do; the folder and the record already agree with "
            "the repository. Nothing was written.")
        return 1 if (unprovable or absent_unprovable) else 0
    written, backups, created = write_files(plan.files, live, stamp, out)
    if written:
        out(f"WROTE   : {len(written)} file(s); each replaced file was copied to "
            f"<name>{BACKUP_SUFFIX}{stamp} beside it before the write")
    errors = compile_written(live, written)
    if errors:
        restore_written(live, backups, created, out)
        out("")
        out("COMPILE FAILED ON THE FILE THAT IS NOW IN THE FOLDER - rolling back:")
        _summ(out, "errors", errors, limit=20)
        raise Refused(f"every file this run wrote ({len(written)}) was put back from its "
                      f"backup; nothing is left half resealed")
    if any(str(n).endswith(".py") for n in written):
        out("COMPILE : py_compile OK for every Python file written")
    if written:
        # Only when something was written: with no write, no bytecode is stale, and a
        # purge would be a change this run did not need to make.
        purged = deploy.purge_pycache(live)
        out(f"PYCACHE : purged {len(purged)} stale .pyc file(s)")

    # 7. Prove convergence with the same comparisons the plan used.
    files_after = plan_files(repo, ref, live, shipped, show=show)
    left = [f for f in files_after if f.changes]
    out("")
    out(f"VERIFY  : {len(left)} of {len(files_after)} shipped file(s) still differ from "
        f"the repository")
    if left:
        _summ(out, "still different", sorted(f.live_name for f in left), limit=20)
        raise Refused("the folder does not hold the repository's bytes after the write; "
                      "the record was NOT touched")
    rows_after, _no_row_after = plan_rows(live, record, files_after)

    # 8. The record last, so a failed write above never leaves a record that blesses it.
    touched = []
    if record:
        try:
            touched = write_record(
                live, record,
                [r for r in rows_after if r.state == "rehash"], rebaseline,
                stamp=stamp, ref=ref, ref_sha=ref_sha, out=out)
        except OSError as exc:
            out("")
            out(f"FAIL  the files were written, but the record could not be updated: {exc}")
            out(f"      The folder is at the repository's bytes; {MANIFEST_NAME} still "
                f"holds the old numbers. Re-run --apply (it is idempotent) or run "
                f"scripts/apply-patches.ps1.")
            return 2
        except Refused as exc:
            out("")
            out(f"FAIL  the files were written, and so was the record, but the record "
                f"does not read back as written: {exc}")
            out(f"      Re-run --apply (it is idempotent); the live folder itself is at "
                f"the repository's bytes.")
            return 2
    if touched:
        out(f"RECORD  : re-hashed {len(touched)} row(s) to the repository's bytes")
    elif record:
        out("RECORD  : no row needed changing")
    else:
        out("RECORD  : no record beside the backend, so nothing in it was changed "
            "(the preflight reports that as a warning, not a failure)")

    # 9. Re-read the record from disk and say what the folder now is.
    final_record, _final_why = read_record(live)
    final_rows, _final_no_row = plan_rows(live, final_record, files_after)
    remaining = [r for r in final_rows if r.state in ("unprovable", "absent-unprovable")]
    out("")
    if patch_stuck:
        # Said whether or not every ROW is now settled: the preflight's patch check is
        # a separate check over separate files, and leaving it out would let a green
        # RESULT here read as a green preflight there.
        out(f"PATCH ROWS the preflight still reports ({len(patch_stuck)}, by the file "
            f"each patch writes) - this tool does not carry these files:")
        for line in _stuck_lines(patch_stuck):
            out(line)
        out("      Those are the patched base files. scripts/apply-patches.ps1 is what "
            "produces them, and #997's tools/repair_live_backend_gaps.py carried the two "
            "pieces it could.")
    if remaining:
        out(f"RESULT: PARTIAL - the folder holds this repository's bytes, and "
            f"{len(remaining)} record row(s) still cannot be proved from it:")
        for row in remaining:
            out(f"      {row.rel}: record {row.want[:12] or '(none)'}, folder "
                f"{row.got_now[:12] or '(absent)'}")
        out("      Those are the patched base files the patch stack owns. Run "
            "scripts/apply-patches.ps1 when it can run, or --rebaseline-unprovable to "
            "record the folder's own bytes deliberately.")
        out("      Restart Jarvis, then run the preflight: the module rows this tool "
            "owns are gone; the ones above are not its to fix.")
        return 1
    if not final_record:
        out("RESULT: PASS - the folder holds this repository's bytes. There is no "
            f"{MANIFEST_NAME} beside it, so the preflight's module check warns rather "
            f"than fails; the patcher writes one on its next finished run.")
    else:
        out("RESULT: PASS - the folder holds this repository's bytes and every record "
            "row agrees with it." + ("" if patch_stuck else " Restart Jarvis, then run "
                                                           "the preflight."))
    if patch_stuck:
        out("      The module rows this tool owns are gone. The patch rows above are "
            "what a preflight may still report, and they move only when the patcher "
            "runs. Restart Jarvis, then run the preflight and read both checks.")
    if backups:
        out(f"        Backups: {len(backups)} file(s) beside themselves with the "
            f"suffix {BACKUP_SUFFIX}{stamp}")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-seal a drifted live Jarvis backend onto the bytes this repository "
                    "ships, and repair the installer's record rows the repository can "
                    "prove (dry run by default).")
    parser.add_argument("--backend-path", required=True,
                        help="the folder holding the live jarvis_hud.py")
    parser.add_argument("--repo", default="",
                        help="the repository checkout (default: this tool's parent folder)")
    parser.add_argument("--ref", default="origin/main",
                        help="the commit whose backend/ blobs are the source "
                             "(default: origin/main)")
    parser.add_argument("--apply", action="store_true",
                        help="write the files and the record; without it this is a dry run")
    parser.add_argument("--dry-run", "--check", dest="dry_run", action="store_true",
                        help="explicit dry run (the default; --check is the same thing)")
    parser.add_argument("--rebaseline-unprovable", action="store_true",
                        help="also record the folder's current hashes for the rows this "
                             "repository cannot prove (the patched base files); off by "
                             "default, and every row it touches is printed")
    ns = parser.parse_args(argv)
    if ns.apply and ns.dry_run:
        print("Choose one: --apply or --dry-run (dry run is the default).")
        return 2
    try:                                    # a non-ASCII path must not crash the report
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    repo = Path(ns.repo) if ns.repo else Path(__file__).resolve().parent.parent
    try:
        return run_reseal(repo, Path(ns.backend_path).expanduser(), apply=bool(ns.apply),
                          ref=ns.ref,
                          rebaseline_unprovable=bool(ns.rebaseline_unprovable))
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2
    except OSError as exc:
        # A read the plan did not wrap (a permission on the live folder, say). Said as
        # one sentence rather than a traceback, and named as "nothing or everything":
        # the only writes that can fail outside their own handler are the ones whose
        # handlers print their own report first.
        print(f"FAILED: {type(exc).__name__}: {exc}")
        print("        If files were being written, their backups are beside them with "
              f"the suffix {BACKUP_SUFFIX}<stamp>; re-run --apply (it is idempotent).")
        return 2
    except KeyboardInterrupt:
        print("Stopped.")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
