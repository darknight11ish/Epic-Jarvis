#!/usr/bin/env python3
"""refresh_patched_base.py - bring ONE patched-base file up to date, provably.

WHY THIS EXISTS (2026-11-19)

`tools/reconcile_live_backend.py` deliberately NEVER carries the five
`PATCHED_FILES` (`jarvis_hud.py`, `jarvis_gate.py`, `jarvis_extract.py`,
`jarvis_models.py`, `jarvis_skills.py`): the live copies are normally NEWER
than the published base, because a patch applied to the install is not in the
base until the base is re-taken. Copying the published base over them would
lose those applied hunks. That rule is right, and this tool does not change it.

But a patched-base file can also fall BEHIND, and then the deploy's cross-file
guard (#1400) refuses - correctly - because a shipped module calls a name the
target folder's patched base file does not bind. That is the 2026-11-18 live
failure: the deploy printed PASS while the live `jarvis_models.py` (a copy
dating from 2026-10-19) had no `ollama_url_on_this_pc`, and `GET /api/presets`
answered 503 with `AttributeError`.

Two hand-written shims were appended to the live `jarvis_models.py` to clear
the guard: `ollama_url_on_this_pc` on 2026-11-18 and `is_pooled_model` +
`probe_refusal` on 2026-11-19. The review ruling (2026-11-19) is that those
two shims are TEMPORARY DEBT TO CLEAR, that NO THIRD SHIM MAY BE ADDED, and
that the clean path is built here. This tool is that clean path. It is a
maintenance pass a person runs against the live folder; it is NOT part of the
deploy, it never runs `apply-patches.ps1`, and it is DRY RUN BY DEFAULT.

WHY NOT TEACH THE DEPLOY TO CARRY THE FILE. That was the other option, and it
is rejected on risk, not on effort. The deploy's rule that these five files are
never written is what makes it safe to run against the only copy of the
program: the deploy's own DELTA_TABLE already EDITS two of them, and a second
writer of the same file in one run would have to prove its whole-file proof and
the delta plan compose - including the owner's drift that the deltas exist for.
The proof below searches the base file's git HISTORY and replays patches; a
mistake in it overwrites the file the patch stack owns. So the refresh stayed a
separate, deliberate, one-file pass with its own backup and its own refusals,
the same shape as `tools/repair_live_backend_gaps.py` (the route the owner's
2026-11-14 ruling gives base-file fixes). The deploy is unchanged: it still
never carries a patched base file, and its cross-file guard is still absolute -
after the refresh it passes only because the target really does bind the names.

WHAT IT PROVES BEFORE IT WRITES (the lineage proof)

The target live file may be refreshed ONLY when its bytes are exactly one of:

  (a) an older PUBLISHED BASE version - a real blob from
      `git log <ref> -- jarvis-backend/<file>`;
  (b) (a) plus a patch set - the `$PATCHES` entries at `--ref` that write this
      file, replayed onto it in `$PATCHES` order, each hunk replacing its own
      pre-image block; or
  (c) (a) or (b) plus ONE CONTIGUOUS SUFFIX of module-level definitions
      appended after the published bytes - the hand-shim shape. The suffix is
      accepted only when EVERY name it binds is
        (i)  NOT bound by the published bytes it was appended to (it really is
             a gap-fill, not a redefinition), and
        (ii) bound by the CURRENT published base (so the base closes the gap).
      Only `def`/`class`/assignment/`import` statements are allowed in the
      suffix (plus comments and docstrings): a top-level CALL or `if` there
      would be code, and dropping it would drop whatever it did. The dry run
      NAMES every suffix definition and says it will be replaced by the
      published base's own definition; `--apply` is for a person who read that
      list. The rule proves the suffix is REDUNDANT once the base binds every
      name it binds; it cannot prove the appended BODIES were correct - that is
      why the report says exactly which definitions are replaced.

A patch that neither applies to the candidate nor is present in it is checked
against `backend/patch-history`: when that patch's OLDER RECORDED VERSION is
present in the candidate, the candidate base simply carries the older shape,
and the CURRENT published base carries the newer one - so the patch is
"baked in", not an unexplained edit. (That is exactly `gpu-offload.patch` on
the 2026-10-06 base and on the owner's live copy: the patch's `_chat_lane_base`
fix was written into the base on 2026-11-08, and the live copy still carries
the 2026-09-15 shape. Replaying today's patch onto it would duplicate
`offload_status()`.)

Anything else is REFUSED and nothing is written: a target that no published
base plus the patch stack explains is a file the deploy's DELTA_TABLE path owns
(its literal deltas, or a hand edit), and this tool must not guess at it.

WHY NOT THE DEPLOY'S DELTA_TABLE PROOF. `reconcile_live_backend.py` decides a
patch is present from probes - a few added lines chosen to be absent from the
patch's own pre-image. That proves ONE patch's presence; a whole-file refresh
needs to know what the WHOLE target is, because the file it writes replaces
every byte. So the proof here is the target's own bytes: a published base
version plus the stack's hunks replayed onto it must equal the target exactly
(and any suffix must be only gap-repair definitions). Probes are never used to
decide that a file may be replaced.

THE NEW FILE

    = the CURRENT published base (`<ref>:jarvis-backend/<file>`), plus any
      patch that IS in the target and is not yet in that base - replayed onto
      it, and it must apply cleanly - and nothing else. Usually it is just the
      base: the base is the state the whole stack last left.

and it is REFUSED rather than written when:

  * the current base would not bind every module-level name the target binds
    (a refresh may ADD names, never LOSE one - the anti-shim direction);
  * the target binds a name through a namespace that cannot be proved static
    (`from ... import *`, a module-level `__getattr__`, `exec()`/`setattr()`);
  * a patch the target carries is neither in the current base nor cleanly
    replayable on it (silently dropping a feature is not allowed);
  * a declared cross-file requirement for this file (the deploy's OWN table -
    it is imported, so the two tools cannot disagree) is not bound;
  * the appended suffix redefines a name the published bytes already bind, or
    binds a name the current base does not;
  * the result does not compile, or the current base has no such file.

USAGE

    py -3 tools/refresh_patched_base.py --backend-path "<live backend>"          # check all five
    py -3 tools/refresh_patched_base.py --backend-path "..." --file jarvis_models.py
    py -3 tools/refresh_patched_base.py --backend-path "..." --file jarvis_models.py --apply

    --file          examine one patched-base file (required with --apply: one
                    write, one backup, one report)
    --apply         write the refresh (without it this is a check; NOTHING is
                    written and no backup is made)
    --ref           the commit whose patch list and published base are used
                    (default `origin/main`; read with `git show`, so the
                    checkout may be at any commit)
    --repo          the repository to read (default: the folder above tools/)
    --json          print the plans as JSON instead of words (for an agent)

WHAT --apply DOES TO THE FILE

It copies the file beside itself to `<name>.before-refresh-<stamp>` (one backup
per file, exactly the `repair_live_backend_gaps.py` convention), writes the new
text to a temporary file in the same folder, compiles it with `py_compile`,
and only then moves it into place. If the compile fails the temporary file is
removed and the original stays untouched, byte for byte. The written file is
then its own sha256 checked and planned again; a second check that is not
"current" is a refusal.

AFTER A REFRESH

Restart Jarvis, then run `py -3 tools/reconcile_live_backend.py --backend-path
"<live>"` - its cross-file guard must now pass for that file, and the deploy is
still the thing that proves the whole folder fits together. A still-missing
name must still refuse: that refusal is the guard this tool exists to satisfy,
not to weaken.

EXIT CODES

    0  every examined file is already the current published base
    1  a refresh is available and was not written (check mode) - run --apply
    2  REFUSED: a file could not be proved, or a write/compile failed; nothing
       was left half-written
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import py_compile
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
#   The deploy tool's own contract, imported rather than copied
# ---------------------------------------------------------------------------
#
# The five patched-base files, the `$PATCHES` parser, the patch hunk reader and
# the module-namespace reader are ALL the deploy tool's. This tool reads them
# from `reconcile_live_backend.py` instead of writing a second copy, so the
# refresh and the deploy's cross-file guard cannot disagree about what a
# "patched base file" is or about which names a file binds. If the deploy tool
# ever renames one of these, this import fails loudly and the test suite names
# it - it never silently degrades.
DEPLOY_TOOL = Path(__file__).resolve().parent / "reconcile_live_backend.py"


def load_deploy_tool():
    """`tools/reconcile_live_backend.py` as a module (no side effects)."""
    spec = importlib.util.spec_from_file_location("refresh_base_deploy_tool",
                                                  DEPLOY_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {DEPLOY_TOOL}")
    module = importlib.util.module_from_spec(spec)
    # dataclasses looks the module up by name while executing it
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


R = load_deploy_tool()

#: The five files the deploy never carries. The refresh is for these and no
#: other file: a shipped module is already carried whole by the deploy.
PATCHED_FILES = tuple(R.PATCHED_FILES)

#: The script whose `$PATCHES` list is the stack.
PATCH_SCRIPT = R.PATCH_SCRIPT
PATCH_HISTORY_INDEX = "backend/patch-history/index.tsv"

#: One sentence a refusal ends with, so a reader knows nothing changed.
NOTHING_WRITTEN = "Refusing rather than guessing; nothing was written."

#: A patch against a candidate text: the three answers `patch_state` gives.
#: They are deliberately a different question from the deploy tool's
#: PRESENT/ABSENT/UNPROVEN: the deploy asks "is this patch already in the
#: file", this tool asks "can this patch be replayed onto it, or is its older
#: recorded shape already in it". The whole-file equality check is what proves
#: the answer in the end.
APPLIED = "applied"
APPLICABLE = "applicable"
UNEXPLAINED = "unexplained"

CURRENT = "current"
REFRESHABLE = "refreshable"
REFUSED = "refused"


class Refused(Exception):
    """The refresh cannot be proved or the write failed; nothing was half-written."""


@dataclass(frozen=True)
class BaseVersion:
    """One PUBLISHED BASE version of one file, from the base file's history."""
    commit: str
    date: str
    subject: str
    text: str


@dataclass(frozen=True)
class PatchText:
    """One `backend/*.patch` entry's own text."""
    name: str
    text: str


@dataclass
class RefreshPlan:
    """Everything one file's check found, and the new bytes when refreshable."""
    file: str
    status: str = CURRENT
    why: str = ""                     # the refusal's own sentence, or ""
    lineage: str = ""                 # one sentence naming the proof
    base_commit: str = ""
    base_date: str = ""
    old_sha256: str = ""
    new_sha256: str = ""
    old_bytes: int = 0
    new_bytes: int = 0
    had_crlf: bool = False
    crlf_count: int = 0
    appended: tuple = ()              # ({"name":..., "kind":...}, ...) - replaced shims
    patches: tuple = ()               # ((patch name, what happened), ...)
    names_lost: tuple = ()
    names_added: tuple = ()
    new_text: str = ""
    required: tuple = ()
    applied: bool = False

    def as_dict(self) -> dict:
        return {
            "file": self.file,
            "status": self.status,
            "why": self.why,
            "lineage": self.lineage,
            "base_commit": self.base_commit,
            "base_date": self.base_date,
            "old_sha256": self.old_sha256,
            "new_sha256": self.new_sha256,
            "old_bytes": self.old_bytes,
            "new_bytes": self.new_bytes,
            "had_crlf": self.had_crlf,
            "crlf_count": self.crlf_count,
            "appended": [dict(item) for item in self.appended],
            "patches": [list(pair) for pair in self.patches],
            "names_lost": list(self.names_lost),
            "names_added": list(self.names_added),
            "required": list(self.required),
            "applied": self.applied,
        }


# ---------------------------------------------------------------------------
#   Reading the repository: git blobs, never the working tree
# ---------------------------------------------------------------------------
#
# Everything the refresh is judged against comes from `--ref`: the file's base
# history, the current base blob, the `$PATCHES` list and the patch texts. The
# working tree's copy is never used - a feature branch's checkout can be behind
# or ahead, and a proof about "the current published base" must mean the commit
# being deployed, not whatever this folder happens to hold.

def git(repo: Path, *args: str, timeout: int = 120) -> bytes:
    """`git -C <repo> <args>` stdout, or a Refused carrying git's own reason."""
    if not shutil.which("git"):
        raise Refused("git is not installed, so the published base's history "
                      "cannot be read. " + NOTHING_WRITTEN)
    try:
        proc = subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, timeout=timeout)
    except Exception as exc:                                  # noqa: BLE001
        raise Refused(f"could not run git {' '.join(args)} "
                      f"({type(exc).__name__}). {NOTHING_WRITTEN}") from exc
    if proc.returncode != 0:
        msg = (proc.stderr or b"").decode("utf-8", "replace").strip()
        raise Refused(f"git {' '.join(args)} failed: {msg or 'no such object'}. "
                      f"{NOTHING_WRITTEN}")
    return proc.stdout


def git_show_text(repo: Path, ref: str, path: str) -> str:
    """One blob at `ref`, decoded exactly (no newline translation)."""
    return git(repo, "show", f"{ref}:{path}").decode("utf-8", "surrogateescape")


def resolve_ref(repo: Path, ref: str) -> str:
    """The full commit SHA `ref` names, or Refused with git's own reason."""
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").decode(
        "ascii", "replace").strip()


def normalize(text: str) -> str:
    """Line endings are not content: compare and write LF.

    Python reads either, and this repository's rule is LF. The live folder may
    hold CRLF (one hand edit appended with an editor that wrote it), and a
    lineage proof must not fail over the difference. The raw file's line ending
    is reported so the change is visible, never silent.
    """
    return str(text).replace("\r\n", "\n")


class RepoFacts:
    """Everything one run reads from `--ref`, each object read at most once.

    The patch stack is about 180 entries and a five-file check needs to know
    which of them write each file; reading each patch once here keeps the run
    to a few seconds instead of five walks of the stack.
    """

    def __init__(self, repo: Path, ref: str):
        self.repo = Path(repo)
        self.ref = ref
        self._patches = None
        self._history_index = None
        self._history = {}

    def patches(self) -> list:
        if self._patches is None:
            script = git_show_text(self.repo, self.ref, PATCH_SCRIPT)
            names = [str(n) for n in R.parse_powershell_list(script, "PATCHES")]
            self._patches = [PatchText(name,
                                       git_show_text(self.repo, self.ref,
                                                     f"backend/{name}"))
                             for name in names]
        return self._patches

    def patches_writing(self, file: str) -> list:
        """The stack entries whose diff writes `file`, in stack order."""
        return [patch for patch in self.patches()
                if file in R.parse_patch_files(patch.text)]

    def history_index(self) -> dict:
        """{patch name: [stored history blob path, newest first]} at the ref."""
        if self._history_index is None:
            index = {}
            try:
                raw = git_show_text(self.repo, self.ref, PATCH_HISTORY_INDEX)
            except Refused:
                raw = ""
            for line in raw.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2 and parts[0]:
                    index.setdefault(parts[0], []).append(parts[1])
            self._history_index = index
        return self._history_index

    def history(self, patch: str) -> list:
        """Every EARLIER recorded version of one patch, newest first.

        `backend/patch-history/index.tsv` is the project's own record (kept
        current by `tools/build_patch_history.py`), and its rows are the only
        proof that a patch's older shape - not the current text - is what a
        published base carries. A missing index is `[]` (no version proved),
        never a guess.
        """
        if patch not in self._history:
            out = []
            for stored in self.history_index().get(patch, ()):
                try:
                    out.append(PatchText(patch, git_show_text(
                        self.repo, self.ref, f"backend/patch-history/{stored}")))
                except Refused:
                    continue
            self._history[patch] = tuple(out)
        return self._history[patch]

    def base_versions(self, file: str) -> list:
        """Every published-base version of `file` reachable from `ref`, newest first.

        This is the candidate list for the lineage proof. A version is a real
        commit in `jarvis-backend/<file>`'s own history: the base's copy is a
        snapshot of the owner's live folder, so one of them is the state the
        file this install has was taken from.
        """
        raw = git(self.repo, "log", "--format=%H%x09%ad%x09%s", "--date=short",
                  self.ref, "--", f"jarvis-backend/{file}").decode(
                      "utf-8", "replace")
        versions = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t", 2)
            if len(parts) != 3:
                raise Refused(f"could not read the base history of {file} "
                              f"(unexpected `git log` line {line[:80]!r}). "
                              f"{NOTHING_WRITTEN}")
            commit, date, subject = parts
            versions.append(BaseVersion(
                commit, date, subject,
                git_show_text(self.repo, commit, f"jarvis-backend/{file}")))
        return versions

    def current_base(self, file: str) -> str:
        """The published base's copy of `file` at the ref - the refresh's bytes."""
        return git_show_text(self.repo, self.ref, f"jarvis-backend/{file}")


# ---------------------------------------------------------------------------
#   Patch replay: can this patch go onto this text, or is it already there?
# ---------------------------------------------------------------------------

def _block(hunk: dict, side: str) -> str:
    return "\n".join(hunk[side])


def hunk_state(text: str, hunk: dict) -> str:
    """APPLIED, APPLICABLE or UNEXPLAINED for ONE hunk against `text`."""
    old, new = _block(hunk, "old"), _block(hunk, "new")
    if old == new:
        return APPLIED
    added = [line for line in hunk["added"] if str(line).strip()]
    if added:
        # Applied means the added lines are in AND the pre-image block is gone.
        # Both halves are needed: a later patch may rewrite only the context,
        # and a removal can re-add a line at another indentation.
        if all(line in text for line in added) and old not in text:
            return APPLIED
    elif old not in text:
        return APPLIED
    if text.count(old) == 1:
        return APPLICABLE
    return UNEXPLAINED


def patch_state(text: str, patch: PatchText, file: str) -> tuple:
    """(state, why) for ONE patch against one file's text.

    APPLIED     - every hunk of the patch is already in the text;
    APPLICABLE  - none is applied and every hunk's pre-image block appears
                  exactly once, so the patch can be replayed hunk by hunk
                  exactly;
    UNEXPLAINED - anything else (a half-applied patch, a shifted block, a
                  version of the patch this text was not cut against).

    A mixed patch - some hunks in, some not - is NEVER "apply the rest": the
    applied half would be applied twice. It falls through to the history check
    or to the refusal.
    """
    hunks = R.patch_hunks(patch.text, file)
    if not hunks:
        return UNEXPLAINED, "the patch has no hunk for this file"
    states = [hunk_state(text, hunk) for hunk in hunks]
    if all(state == APPLIED for state in states):
        return APPLIED, "every hunk is already in the text"
    if all(state == APPLICABLE for state in states):
        return APPLICABLE, "every hunk's pre-image block is present exactly once"
    return UNEXPLAINED, (f"{states.count(APPLIED)} of its {len(states)} hunk(s) "
                         f"are in the text and {states.count(APPLICABLE)} could "
                         f"be applied; it is half applied, which no refresh may "
                         f"guess at")


def replay_patch(text: str, patch: PatchText, file: str) -> str:
    """Apply every hunk's pre-image -> post-image replacement, in order.

    Refused if any pre-image block is missing or appears more than once: a
    guess here is a block inserted in the wrong place, which is how a route
    lands in the wrong dispatch chain.
    """
    for index, hunk in enumerate(R.patch_hunks(patch.text, file), 1):
        old, new = _block(hunk, "old"), _block(hunk, "new")
        if old == new:
            continue
        count = text.count(old)
        if count != 1:
            raise Refused(f"{patch.name}: hunk {index}'s pre-image block appears "
                          f"{count} time(s) in the text; expected exactly 1. "
                          f"{NOTHING_WRITTEN}")
        text = text.replace(old, new, 1)
    return text


def _history_proves_baked_in(patch: PatchText, history: Iterable[PatchText],
                             text: str, file: str) -> bool:
    """True when an OLDER RECORDED version of `patch` is present in `text`.

    `gpu-offload.patch` on the owner's live copy is the worked case. The live
    file carries the patch as it was on 2026-09-15 (its `offload_status()`),
    which the 2026-10-06 published base also carries; the current patch text
    (rewritten 2026-11-08 to add `_chat_lane_base()`) can neither be replayed
    onto that text nor found in it. That is NOT an unexplained edit: the older
    patch is recorded in `backend/patch-history`, and the current base carries
    the newer shape. So the candidate is "an older published base whose stack
    was older than today's", which is exactly what a published base version is.
    """
    for old in history:
        state, _why = patch_state(text, old, file)
        if state == APPLIED:
            return True
    return False


def _replayed_note(details) -> str:
    """", with N patch(es) replayed in $PATCHES order" for a lineage sentence."""
    replayed = [name for name, what in details
                if what == "replayed onto this base version"]
    if not replayed:
        return ""
    return (f", plus {len(replayed)} patch(es) replayed in $PATCHES order "
            f"({', '.join(replayed)})")


def build_candidate(version: BaseVersion, patches: list, history: dict,
                    file: str) -> tuple:
    """(text or None, details, why) - one base version + the patches after it.

    `details` is ((patch name, what happened), ...); `why` names the first
    patch that does not fit. The caller compares the result to the target: the
    whole-file equality is the proof, not any single patch's verdict.
    """
    text = version.text
    details = []
    for patch in patches:
        state, why = patch_state(text, patch, file)
        if state == APPLIED:
            details.append((patch.name, "already in this base version"))
            continue
        if state == APPLICABLE:
            text = replay_patch(text, patch, file)
            details.append((patch.name, "replayed onto this base version"))
            continue
        if _history_proves_baked_in(patch, history.get(patch.name, ()),
                                    text, file):
            details.append((patch.name,
                            "this base version carries the patch's OLDER "
                            "recorded shape"))
            continue
        return None, details, f"{patch.name}: {why}"
    return text, details, ""


# ---------------------------------------------------------------------------
#   The appended block: the two hand shims are REPLACED, not kept
# ---------------------------------------------------------------------------

def appended_definitions(suffix: str, file: str) -> list:
    """[{"name":..., "kind":...}] for the definitions in an appended suffix.

    Refuses any statement that is not a definition (see `_SUFFIX_STATEMENTS`):
    a top-level call, `if` or `try` in an appended block is code with an
    EFFECT, and a refresh that removes it would remove that effect. The suffix
    this tool accepts is the "deploy gap repair" shape - plain `def`s whose
    names the published base now provides.
    """
    try:
        tree = ast.parse(suffix)
    except SyntaxError as exc:
        raise Refused(f"{file}: the {len(suffix)} byte(s) appended after the "
                      f"published base are not valid Python ({exc.msg}, line "
                      f"{exc.lineno}); {NOTHING_WRITTEN}") from exc
    out = []
    for node in tree.body:
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, (str, type(None)))):
            continue                      # a bare docstring / literal: no effect
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            out.append({"name": node.name, "kind": type(node).__name__})
            continue
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets
                     if isinstance(target, ast.Name)]
            if len(names) != len(node.targets):
                raise Refused(f"{file}: the appended block assigns to something "
                              f"other than a plain name; {NOTHING_WRITTEN}")
            out.extend({"name": name, "kind": "assignment"} for name in names)
            continue
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.append({"name": node.target.id, "kind": "assignment"})
            continue
        if isinstance(node, ast.Import):
            out.extend({"name": alias.asname or alias.name.split(".")[0],
                        "kind": "import"} for alias in node.names)
            continue
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == "*" for alias in node.names):
                raise Refused(f"{file}: the appended block has a "
                              f"'from ... import *', which binds names this tool "
                              f"cannot enumerate; {NOTHING_WRITTEN}")
            out.extend({"name": alias.asname or alias.name,
                        "kind": "from-import"} for alias in node.names)
            continue
        raise Refused(
            f"{file}: the {len(suffix)} byte(s) appended after the published "
            f"base are not only definitions - one statement is a "
            f"{type(node).__name__}. An appended block is accepted only when it "
            f"is a gap-repair of module-level definitions; running code dropped "
            f"from the file could have an effect. {NOTHING_WRITTEN}")
    return out


# ---------------------------------------------------------------------------
#   Names: the deploy tool's own reader, so the two tools cannot disagree
# ---------------------------------------------------------------------------

def namespace(text: str, file: str) -> frozenset:
    """The module-level names a file binds, or Refused when not provable.

    This is the deploy tool's own reader, so "the refresh did not lose a name"
    and "the cross-file guard can back every name" are judged by one function.
    """
    try:
        names, unproven = R.module_level_names(text)
    except SyntaxError as exc:
        raise Refused(f"{file}: the text is not valid Python ({exc.msg}, line "
                      f"{exc.lineno}); {NOTHING_WRITTEN}") from exc
    if unproven:
        raise Refused(f"{file}: its namespace cannot be proved static - "
                      f"{unproven}. A refresh cannot prove it would lose "
                      f"nothing, so it is refused. {NOTHING_WRITTEN}")
    return names


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest()


def _compile_text(text: str, file: str) -> None:
    """py_compile the text as `file` in a temporary folder; Refused on failure."""
    tmp = Path(tempfile.mkdtemp(prefix="refresh-base-rehearsal-"))
    try:
        path = tmp / file
        path.write_text(text, encoding="utf-8", errors="surrogateescape",
                        newline="\n")
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            raise Refused(f"{file}: the refreshed text does not compile "
                          f"({exc.msg}); {NOTHING_WRITTEN}") from exc
        except Exception as exc:                              # noqa: BLE001
            raise Refused(f"{file}: the refreshed text does not compile "
                          f"({type(exc).__name__}: {exc}); {NOTHING_WRITTEN}") \
                from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
#   The decision (pure: fixtures prove this without git or the owner's PC)
# ---------------------------------------------------------------------------

def plan_refresh(file: str, live_raw: str, versions, patches, history,
                 base_now: str,
                 required_names: Iterable[str] = ()) -> RefreshPlan:
    """The whole decision for one file. Reads nothing; writes nothing.

    `versions`, `patches`, `history` and `base_now` are supplied, so a fixture
    needs no git object store and no owner's PC; `main` supplies the same
    values read from `--ref`.
    """
    if file not in PATCHED_FILES:
        raise Refused(f"{file!r} is not one of the five patched base files "
                      f"({', '.join(PATCHED_FILES)}); the deploy carries every "
                      f"other file already. {NOTHING_WRITTEN}")
    live = normalize(live_raw)
    target = normalize(base_now)
    if not target.strip():
        raise Refused(f"the published base has no {file}; {NOTHING_WRITTEN}")
    plan = RefreshPlan(
        file=file,
        old_sha256=_sha256(live),
        new_sha256=_sha256(target),
        old_bytes=len(live.encode("utf-8", "surrogateescape")),
        new_bytes=len(target.encode("utf-8", "surrogateescape")),
        had_crlf="\r\n" in str(live_raw),
        crlf_count=str(live_raw).count("\r\n"),
        required=tuple(required_names))
    if live == target:
        plan.status = CURRENT
        plan.lineage = (
            f"{file} is already the current published base "
            f"(jarvis-backend/{file} at the ref), byte for byte"
            if not plan.had_crlf else
            f"{file} is the current published base after line-ending "
            f"normalisation; no bytes were written")
        return plan

    # -- the lineage proof --------------------------------------------------
    core = cover = None
    details = []
    matched = None
    attempts = []
    for index, version in enumerate(versions):
        candidate, candidate_details, why = build_candidate(
            version, patches, history, file)
        if candidate is None:
            attempts.append(f"{version.commit[:9]} ({version.date}): {why}")
            continue
        if live == candidate:
            core, cover, details, matched = live, "", candidate_details, version
            plan.lineage = (
                f"the target is jarvis-backend/{file} at "
                f"{version.commit[:9]} ({version.date}, {version.subject!r})"
                + _replayed_note(candidate_details))
            break
        if (live.startswith(candidate) and candidate.endswith("\n")
                and len(candidate) < len(live)):
            # A suffix is only a gap repair relative to the TRUE ancestor. If a
            # NEWER published version's own bytes are a prefix of the target, the
            # target grew out of THAT version (or later), and this older one
            # cannot explain what follows it - so do not accept a suffix here.
            newer_prefix = any(
                live.startswith(normalize(older.text))
                and len(normalize(older.text)) < len(live)
                for older in versions[:index])
            if newer_prefix:
                attempts.append(
                    f"{version.commit[:9]} ({version.date}): a NEWER published "
                    f"version's bytes are a prefix of the target, so this older "
                    f"version cannot explain the rest")
                continue
            core, cover = candidate, live[len(candidate):]
            details, matched = candidate_details, version
            plan.lineage = (
                f"the target is jarvis-backend/{file} at "
                f"{version.commit[:9]} ({version.date}, {version.subject!r})"
                + _replayed_note(candidate_details)
                + f" plus {len(cover)} appended byte(s)")
            break
        attempts.append(f"{version.commit[:9]} ({version.date}): the target is "
                        f"not this version plus its patches")
    if core is None:
        plan.status = REFUSED
        tried = ""
        if attempts:
            shown = "; ".join(attempts[:2])
            older = len(attempts) - 2
            tried = (f". Tested, newest published version first: {shown}"
                     + (f"; and {older} older version(s), each tried the same "
                        f"way" if older > 0 else ""))
        plan.why = (
            f"the target is not any published base of jarvis-backend/{file}, "
            f"nor one plus the $PATCHES entries that write it, replayed{tried}. "
            f"So its bytes include content this tool cannot derive. The usual "
            f"cause is that the target is NEWER than the newest published base "
            f"(the install carries patches the base has not been re-taken with) "
            f"- the deploy's DELTA_TABLE path owns that case - or the target "
            f"holds a hand edit. Neither is something a whole-file refresh may "
            f"guess at. {NOTHING_WRITTEN}")
        return plan

    plan.base_commit = matched.commit
    plan.base_date = matched.date

    # -- what the current base would be -------------------------------------
    core_names = namespace(core, file)
    new = target
    steps = []
    for patch in patches:
        state, why = patch_state(core, patch, file)
        if state == APPLIED:
            base_state, _base_why = patch_state(new, patch, file)
            if base_state == APPLIED:
                steps.append((patch.name, "already in the current base"))
            elif base_state == APPLICABLE:
                new = replay_patch(new, patch, file)
                steps.append((patch.name, "replayed onto the current base"))
            else:
                plan.status = REFUSED
                plan.why = (
                    f"the target carries {patch.name}, and the current "
                    f"published base neither carries it nor can take it "
                    f"cleanly ({why}), so a refresh would DROP that patch's "
                    f"feature. {NOTHING_WRITTEN}")
                return plan
        elif _history_proves_baked_in(patch, history.get(patch.name, ()),
                                      core, file):
            steps.append((patch.name,
                          "the target carries its older shape; the current "
                          "base carries the newer shape"))
        elif patch_state(new, patch, file)[0] == APPLIED:
            steps.append((patch.name,
                          "not in the target; the current base carries it"))
        else:
            steps.append((patch.name,
                          "not in the target, and not in the current base "
                          "either - the deploy's delta plan carries it"))
    new_names = namespace(new, file)

    # -- safety: a refresh may add a name, never lose one -------------------
    plan.names_lost = tuple(sorted(core_names - new_names))
    plan.names_added = tuple(sorted(new_names - core_names))
    if plan.names_lost:
        plan.status = REFUSED
        plan.why = (
            f"the current published base does not bind "
            f"{', '.join(repr(n) for n in plan.names_lost)}, which the target "
            f"does. A refresh must never lose a name; refusing to drop "
            f"{len(plan.names_lost)} name(s). {NOTHING_WRITTEN}")
        return plan

    # -- the appended block: THE TWO HAND SHIMS ARE REPLACED HERE -----------
    if cover is not None and cover.strip():
        appended = appended_definitions(cover, file)
        suffix_names = frozenset(item["name"] for item in appended)
        redefined = sorted(suffix_names & core_names)
        if redefined:
            plan.status = REFUSED
            plan.why = (
                f"the target has {len(cover)} byte(s) appended after the "
                f"published base, and they redefine "
                f"{', '.join(repr(n) for n in redefined)} - names the published "
                f"bytes already bind. That is not a gap repair, and removing it "
                f"would change behaviour this tool cannot prove. "
                f"{NOTHING_WRITTEN}")
            return plan
        unclosed = sorted(suffix_names - new_names)
        if unclosed:
            plan.status = REFUSED
            plan.why = (
                f"the target has {len(cover)} byte(s) appended after the "
                f"published base, and they define "
                f"{', '.join(repr(n) for n in unclosed)}, which the current "
                f"published base does not. Refreshing would REMOVE "
                f"{len(unclosed)} name(s) - that would be losing a fix, not "
                f"replacing a gap repair. {NOTHING_WRITTEN}")
            return plan
        plan.appended = tuple(appended)
        plan.lineage += (f"; {len(appended)} appended definition(s) are "
                         f"replaced by the published base's own")
    elif cover:
        plan.lineage += ", with only trailing whitespace/comments after it"

    # -- declared cross-file requirements, from the deploy's own table ------
    missing_required = [name for name in plan.required if name not in new_names]
    if missing_required:
        plan.status = REFUSED
        plan.why = (
            f"the current published base does not bind the deploy's declared "
            f"cross-file requirement(s) "
            f"{', '.join(repr(n) for n in missing_required)} for {file}, so a "
            f"refresh would not satisfy the guard it exists for. "
            f"{NOTHING_WRITTEN}")
        return plan

    # -- the new file must be real Python -----------------------------------
    try:
        _compile_text(new, file)
    except Refused as exc:
        plan.status = REFUSED
        plan.why = str(exc)
        return plan

    plan.status = REFRESHABLE
    plan.new_text = new
    plan.new_bytes = len(new.encode("utf-8", "surrogateescape"))
    plan.new_sha256 = _sha256(new)
    plan.patches = tuple(steps)
    return plan


# ---------------------------------------------------------------------------
#   The one write: backup beside the file, temp compile, then swap
# ---------------------------------------------------------------------------

def apply_refresh(live: Path, plan: RefreshPlan, *,
                  stamp: Optional[str] = None) -> Path:
    """Write `plan.new_text` over `<live>/<file>`, with one backup.

    Returns the backup path. The order is: back up, write a temporary file
    beside the target, compile it, and only then move it into place. A compile
    failure removes the temporary and leaves the original byte for byte.
    """
    if plan.status != REFRESHABLE:
        raise Refused(f"{plan.file}: nothing to apply (status {plan.status!r})")
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    path = Path(live) / plan.file
    if not path.is_file():
        raise Refused(f"{live} has no {plan.file}; {NOTHING_WRITTEN}")
    backup = path.with_name(path.name + f".before-refresh-{stamp}")
    shutil.copy2(path, backup)
    fd, tmpname = tempfile.mkstemp(prefix=path.name + ".",
                                   suffix=".refresh-tmp", dir=str(live))
    try:
        with open(fd, "w", encoding="utf-8", errors="surrogateescape",
                  newline="\n") as fh:
            fh.write(plan.new_text)
        py_compile.compile(tmpname, doraise=True)
        shutil.move(tmpname, str(path))
    except Exception as exc:                                  # noqa: BLE001
        try:
            shutil.copy2(backup, path)
        finally:
            Path(tmpname).unlink(missing_ok=True)
        raise Refused(f"{plan.file}: the refreshed file did not compile; the "
                      f"original was restored from {backup.name}") from exc
    read_back = normalize(path.read_bytes().decode("utf-8", "surrogateescape"))
    if _sha256(read_back) != plan.new_sha256:
        shutil.copy2(backup, path)
        raise Refused(f"{plan.file}: the bytes read back after the write are "
                      f"not the bytes that were proved; the original was "
                      f"restored from {backup.name}")
    return backup


# ---------------------------------------------------------------------------
#   A report a person can read
# ---------------------------------------------------------------------------

def _bytes_count(n: int) -> str:
    return f"{n:,}"


def report_plan(plan: RefreshPlan, *, done: bool = False,
                backup: Optional[Path] = None) -> list:
    """The report for one file, as lines. A refused plan prints its reason."""
    lines = [f"  {plan.file}"]
    if plan.status == CURRENT:
        lines.append(f"    current    {plan.lineage}.")
        return lines
    if plan.status == REFUSED:
        lines.append(f"    REFUSED    {plan.why}")
        return lines
    lines.append(f"    lineage    PROVED: {plan.lineage}.")
    if plan.patches:
        lines.append("    patches    " + "; ".join(
            f"{name}: {what}" for name, what in plan.patches))
    if plan.appended:
        lines.append(
            "    appended   "
            + ", ".join(f"{item['name']} ({item['kind']})"
                        for item in plan.appended)
            + " - each name is bound by the current published base, so the "
              "refresh REPLACES these hand-written definitions with the base's "
              "own")
    else:
        lines.append("    appended   none - the target ends where its published "
                     "base ends")
    lines.append(f"    names      +{len(plan.names_added)} added, 0 lost"
                 + (f" ({', '.join(plan.names_added)})" if plan.names_added
                    else ""))
    lines.append(f"    bytes      {_bytes_count(plan.old_bytes)} -> "
                 f"{_bytes_count(plan.new_bytes)}"
                 + (f" (the target contains {plan.crlf_count} CRLF line "
                    f"ending(s); the refresh writes LF, the repository's "
                    f"rule)" if plan.had_crlf else ""))
    if plan.required:
        lines.append("    guard      the deploy's declared cross-file "
                     "requirement(s) "
                     + ", ".join(plan.required)
                     + " are all bound by the refreshed file")
    lines.append(f"    sha256     {plan.old_sha256[:12]} -> "
                 f"{plan.new_sha256[:12]}")
    if done:
        lines.append(f"    WRITTEN    the file was refreshed; backup kept at "
                     f"{backup}")
        lines.append("    next       restart Jarvis, then run the deploy's dry "
                     "run: its cross-file")
        lines.append("               guard must pass for this file, and the "
                     "deploy is still what")
        lines.append("               proves the whole folder fits together")
    else:
        lines.append(f"    ready      the dry run wrote NOTHING; "
                     f"--file {plan.file} --apply writes it")
    return lines


def print_plan(plan: RefreshPlan, *, done: bool = False,
               backup: Optional[Path] = None) -> None:
    for line in report_plan(plan, done=done, backup=backup):
        print(line)


# ---------------------------------------------------------------------------
#   main
# ---------------------------------------------------------------------------

def declared_requirements(file: str) -> tuple:
    """The deploy's declared cross-file names for `file` (its own table)."""
    return tuple(dep.name for dep in R.CROSS_FILE_DEPENDENCIES
                 if dep.file == file)


def read_live(live: Path, file: str) -> str:
    path = Path(live) / file
    if not path.is_file():
        raise Refused(f"{live} has no {file}, so there is no patched base file "
                      f"to refresh; {NOTHING_WRITTEN}")
    try:
        return path.read_bytes().decode("utf-8", "surrogateescape")
    except OSError as exc:
        raise Refused(f"{file} could not be read ({exc}); {NOTHING_WRITTEN}") \
            from exc


def plan_one(facts: RepoFacts, live: Path, file: str) -> RefreshPlan:
    """Read the ref through `facts` and plan one file. Nothing is written."""
    writing = facts.patches_writing(file)
    return plan_refresh(
        file, read_live(live, file),
        facts.base_versions(file), writing,
        {patch.name: facts.history(patch.name) for patch in writing},
        facts.current_base(file),
        required_names=declared_requirements(file))


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Bring one patched-base file up to the published base, "
                    "provably. Dry run by default.")
    ap.add_argument("--backend-path", required=True,
                    help="the folder holding the live jarvis_hud.py")
    ap.add_argument("--file", default="", choices=["", *PATCHED_FILES],
                    help="the one patched-base file to examine (required with "
                         "--apply)")
    ap.add_argument("--apply", action="store_true",
                    help="write the refresh (without it this is a check)")
    ap.add_argument("--ref", default="origin/main",
                    help="the commit whose base and patch list are used "
                         "(default origin/main)")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent),
                    help="the repository to read the base history from")
    ap.add_argument("--json", action="store_true",
                    help="print the plans as JSON (the words are then omitted)")
    ns = ap.parse_args(argv)
    live = Path(ns.backend_path).expanduser()
    repo = Path(ns.repo).expanduser()
    if not live.is_dir():
        print(f"REFUSED: {live} is not a folder; nothing was written.")
        return 2
    if ns.apply and not ns.file:
        print("REFUSED: --apply writes ONE file at a time; pass --file <name> "
              "(" + ", ".join(PATCHED_FILES) + "). Nothing was written.")
        return 2
    try:
        facts = RepoFacts(repo, ns.ref)
        sha = resolve_ref(repo, ns.ref)
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2
    files = [ns.file] if ns.file else list(PATCHED_FILES)
    if not ns.json:
        print(f"published base: {ns.ref} = {sha[:12]}")
        print(f"target:         {live}")
        print("mode:           "
              + ("APPLY - a write is allowed for the chosen file"
                 if ns.apply else "dry run - nothing is written"))
        print()
    plans = []
    results = []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for file in files:
        try:
            plan = plan_one(facts, live, file)
        except Refused as exc:
            if not ns.json:
                print(f"  {file}\n    REFUSED    {exc}\n")
            results.append({"file": file, "status": REFUSED, "why": str(exc)})
            continue
        if ns.apply and plan.status == REFRESHABLE:
            try:
                backup = apply_refresh(live, plan, stamp=stamp)
                # The write stands only when it plans as CURRENT: re-read the
                # written file and prove it is the base, not merely that the
                # bytes were copied.
                again = plan_one(facts, live, file)
                if again.status != CURRENT:
                    shutil.copy2(backup, Path(live) / file)
                    raise Refused(
                        f"{file}: the written file does not plan as current on a "
                        f"second check ({again.status}: {again.why}); the "
                        f"original was restored from {backup.name}")
            except Refused as exc:
                if not ns.json:
                    print(f"  {file}\n    REFUSED    {exc}\n")
                results.append({"file": file, "status": REFUSED,
                                "why": str(exc)})
                continue
            plan.applied = True
            if not ns.json:
                print_plan(plan, done=True, backup=backup)
                print()
        elif not ns.json:
            print_plan(plan, done=False, backup=None)
            print()
        plans.append(plan)
        results.append(plan.as_dict())
    current = sum(1 for plan in plans
                  if plan.status == CURRENT and not plan.applied)
    refreshable = sum(1 for plan in plans
                      if plan.status == REFRESHABLE and not plan.applied)
    written = sum(1 for plan in plans if plan.applied)
    refused = sum(1 for result in results if result["status"] == REFUSED)
    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        print(f"RESULT: {current} current, {refreshable} refreshable, "
              f"{refused} refused"
              + (f", {written} written" if ns.apply else
                 " - the dry run wrote NOTHING"))
    if refused:
        print("A refused file is one this tool cannot prove; it is NOT a pass. "
              "The reason is printed above and nothing was written for it.")
        return 2
    if not ns.apply and refreshable:
        print("Re-run with --file <name> --apply for the file you choose.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
