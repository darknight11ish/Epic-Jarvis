#!/usr/bin/env python3
"""reconcile_live_backend.py - deploy the repository's backend onto a live Jarvis folder, safely.

WHY THIS EXISTS
    The 2026-10-20 deploy was done by two hand-written throwaway scripts
    (`.dsh-scratch/reconcile-hud-2026-10-20.py`, `reconcile-setup-2026-10-20.py`). This
    is that work made reusable, and it answers Gemini's review: sync what the repository
    ships, add only the HUD deltas that are genuinely missing, rehearse before swapping,
    back up everything it overwrites, clear stale bytecode, add the ready plug-ins, then
    prove the routes with the live server.

    It is DRY-RUN BY DEFAULT. `--apply` is the only thing that writes.

WHAT IT DOES, IN ORDER (see --help and the summary it prints)

    1. SHIPPED SYNC. Reads the authoritative `$SHIPPED` list out of
       `scripts/apply-patches.ps1` (the same extraction the deploy used), flattens
       `rebuilt/<name>` to the live base name, compares each file with
       `origin/main:backend/<path>` BY BYTES, and copies only changed or missing files.
       Every file it overwrites is first copied into
       `<live>/_jarvis-deploy-backup-tool-<stamp>/`. It writes the repository's bytes
       exactly, so LF stays LF and no line-ending rewriting happens.
       `jarvis-backend/*` is NEVER copied over live: that folder is a stale 2026-10-14
       snapshot (`.dsh-scratch/LINEAGE-CORRECTION-2026-10-20.md`), not a runtime tree.

    A failed APPLY is fail-closed and journaled. The backup folder and its
    `_journal.json` are created and PRINTED before the first live write; a write
    failure or a failed ready plug-in restores every overwritten file and removes
    every path this run created, then exits non-zero. A route-probe failure is
    different by design: it happens only after a COMPLETE write, so the new files
    are kept and the report prints the backup/journal plus the exact
    `--rollback <backup folder>` command (a running server is not un-deployed
    underneath the operator). `--rollback` restores a backup folder's journal
    without deploying anything.
    2. HUD DELTAS for the five patched base files (`jarvis_hud.py`, `jarvis_gate.py`,
       `jarvis_extract.py`, `jarvis_models.py`, `jarvis_skills.py`). Those files are
       never replaced, because the live copies are newer than the published base. For
       every `.patch` in `$PATCHES` that touches one of them, the tool decides
       ALREADY_PRESENT from that patch's distinctive added lines; when absent it inserts
       the patch's added lines at the logical anchor the stack uses. The anchors are a
       small data table (`DELTA_TABLE`) - today app-control's route block before
       `if route == "/api/memory/decide":`, setup's install block and plugin-loader's
       block in their stack order. A patch that is absent, touches a patched file, and
       has no anchor rule is REFUSED loudly: the tool changes nothing and names the
       patch, the file and what it would need. A missing or ambiguous anchor is refused
       the same way - it never guesses. A delta whose live anchor does not exist at all
       (F10 `traces.db` retention, Q2) is recorded in `BLOCKED_DELTAS` with its evidence,
       printed as BLOCKED LIVE DELTAS, and never staged: blocked is reported, not guessed.
       Fixes that live in the published base files but in NO `.patch` of their own
       are literal deltas too: the entry carries the exact block bytes in
       `tools/hud-deltas/` and either inserts them at an anchor or REPLACES an old
       block that must appear exactly once. The literal loop is not HUD-only - it
       iterates whatever file an entry names, so any of the five patched files can
       be carried this way (the 2026-10-14 HUD fixes do it for `jarvis_hud.py`;
       review ruling 8.2's guard change does it for `jarvis_gate.py` in four
       entries, because `gate-touches.patch` is already in the live patch list and
       its new hunks would otherwise be reported ALREADY_PRESENT and never deploy).

    3. REHEARSAL. Every staged Python file is compiled with `py_compile` before any live
       file is touched. If compilation fails, nothing is written.

    4. PYCACHE PURGE. `__pycache__/*.pyc` in the live folder is deleted after the write,
       so a changed module cannot run from stale bytecode (the `jarvis_speech` trap).

    5. READY PLUG-INS. Every `plugins/ready/<name>/plugin.json` that is not already in
       `<live>/jarvis_plugins/<name>` is added by running
       `scripts/add-plugin.ps1 -BackendPath <live> -Name <name>` non-interactively.
       One safety guard: if the live `jarvis_hud.py` already calls that module's own
       `install()` (the patch stack wired the feature), the folder is NOT added - a
       second call would double-wire the same feature - and the run says SKIP, with the
       module named. Only genuinely unwired ready plug-ins are added. `--skip-plugins`
       leaves this step out.

    6. ROUTE PROBES. With the HUD token read by `python jarvis_token_store.py show` in
       the live folder (never printed), it sends `X-Jarvis-Client: hud` and probes:
         GET  /api/setup            -> 200
         GET  /api/media-index      -> 200, only when the media-index plug-in is present
         POST /api/app-control/run  -> 409 while `[app_control]` is absent (it may be)
         GET  /api/voice/status     -> 200 and `gate.training` present
       It prints PASS / FAIL / SKIP per probe and exits non-zero if an expected probe
       fails.

    A second `--apply` on an already-current tree changes nothing and all probes pass.

WHAT IT DOES NOT DO
    * It never runs the patch script and never edits `scripts/apply-patches.ps1`.
    * It never copies `jarvis-backend/*` over live and has no code path that reads it.
    * It never writes a token, prints one, or puts one in the report.
    * It does not restart Jarvis; restart after it and read the start-up banner.
    * It does not handle the non-Python "beside-files" (requirements.lock etc.) that
      apply-patches.ps1 carries; the $SHIPPED list is the contract this tool follows.

USAGE
    py -3 tools/reconcile_live_backend.py --backend-path "<live backend>"            # dry run
    py -3 tools/reconcile_live_backend.py --backend-path "<live backend>" --apply
    py -3 tools/reconcile_live_backend.py --backend-path ... --apply --skip-plugins

EXIT CODES
    0 success (dry run planned cleanly, or apply + all probes PASS)
    1 a plugin add or a route probe failed
    2 refused before writing (bad arguments, unknown HUD delta, missing anchor, rehearsal)
"""
from __future__ import annotations

import argparse
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Optional

# ---------------------------------------------------------------------------
#   Constants that describe the repository's deploy contract
# ---------------------------------------------------------------------------

#: The five patched base files: the live copies are newer, so they are never replaced.
PATCHED_FILES = ("jarvis_hud.py", "jarvis_gate.py", "jarvis_extract.py",
                 "jarvis_models.py", "jarvis_skills.py")

#: Where the stack puts the setup block: before the plugin-loader block, which is LAST.
PLUGIN_LOADER_MARKER = "    # plugin-loader.patch (this branch)."

#: The POST route-dispatch line app-control's route block goes in front of.
APP_CONTROL_ANCHOR = '        if route == "/api/memory/decide":'

#: The line plugin-loader's install block goes in front of.
BEFORE_SOCKET = "    # Before the main socket, so the banner lists every address together."

#: The HUD fixes that live in the published base HUD but in NO `.patch` - so
#: `$PATCHES` never carries them - are literal deltas below: DEF-002's status
#: cache (its block, its start call and the route that reads it) and the
#: 2026-10-14 reasoning fallback. The block text is read from
#: `tools/hud-deltas/`, extracted from the base and the live file, so this tool
#: carries bytes rather than a paraphrase.
_DELTA_DIR = Path(__file__).resolve().parent / "hud-deltas"


def _delta_lines(name: str) -> tuple:
    """The exact lines of one literal delta block, newline-style normalised."""
    text = (_DELTA_DIR / name).read_text(encoding="utf-8", errors="replace")
    return tuple(text.replace("\r\n", "\n").splitlines())


#: DEF-002: insert the cache + poller block immediately before the Brain graph
#: section, and start the poller from main() before the engine globals.
STATUS_CACHE_ANCHOR = "# Brain graph"
STATUS_START_ANCHOR = "    global _ENGINE, _PUMP"
STATUS_CACHE_FILE = "status-cache.txt"
STATUS_START_FILE = "status-start.txt"

#: reasoning-fallback: replace the old inline relay loop with the wrapped one
#: that shows a reasoning-only cloud answer instead of a blank card.
REASONING_OLD_FILE = "reasoning-old.txt"
REASONING_NEW_FILE = "reasoning-new.txt"

#: DEF-002's third piece: the /api/status ROUTE itself, replaced by the base's
#: cached one. #668's deltas inserted only the cache block and its start call, so
#: the live route still probed upstream inline - measured 3094/3117 ms plain and
#: 3084/3097 ms with `?force=1` (2026-10-20), i.e. the flag was ignored because
#: the old route has no force handling. The old block must appear exactly once.
STATUS_ROUTE_OLD_FILE = "status-route-old.txt"
STATUS_ROUTE_NEW_FILE = "status-route-new.txt"

#: Review ruling 8.2's guard change (PR #680) reaches the live PC the same way
#: the two HUD fixes do, and for a reason that reads like a silent trap:
#: `gate-touches.patch` is ALREADY in the live `_jarvis-state.json` patch list,
#: so the stack walk reports it ALREADY_PRESENT - and its new hunks (the
#: pending-card dedup guard and the `replaces` flag) would never be deployed.
#: So the change is carried as literal deltas, one per disjoint region of
#: `jarvis_gate.py`; each old block is the text the owner's live gate holds and
#: must appear there EXACTLY once (a half-applied file is refused, never
#: guessed). The bytes were extracted from the published base gate before and
#: after PR #680; the four deltas together reconstruct the published file byte
#: for byte (`backend/test_reconcile_live_backend.py` proves it).
GATE_GUARDS_IMPORT_OLD_FILE = "gate-guards-import-old.txt"
GATE_GUARDS_IMPORT_NEW_FILE = "gate-guards-import-new.txt"
GATE_GUARDS_HELPERS_NEW_FILE = "gate-guards-helpers-new.txt"
GATE_GUARDS_DEDUP_OLD_FILE = "gate-guards-dedup-old.txt"
GATE_GUARDS_DEDUP_NEW_FILE = "gate-guards-dedup-new.txt"
GATE_GUARDS_REPLACES_OLD_FILE = "gate-guards-replaces-old.txt"
GATE_GUARDS_REPLACES_NEW_FILE = "gate-guards-replaces-new.txt"

#: F-680-2 (2026-10-21 pre-merge audit): the long-detail dedupe fix, carried to
#: the live `jarvis_gate.py` as three more literal deltas. Their OLD blocks are
#: the POST-#688 gate - what the four guard deltas above leave in the staged
#: text - so these entries are ordered after theirs in `DELTA_TABLE` and see
#: the same staged copy. Extracted from the published base gate before and
#: after this fix; together they reconstruct the published file byte for byte
#: (`backend/test_reconcile_live_backend.py` proves it, and a real-live dry run
#: plans exactly these inserts with no refusal).
GATE_DIGEST_INIT_OLD_FILE = "gate-digest-init-old.txt"
GATE_DIGEST_INIT_NEW_FILE = "gate-digest-init-new.txt"
GATE_DIGEST_PENDING_OLD_FILE = "gate-digest-pending-old.txt"
GATE_DIGEST_PENDING_NEW_FILE = "gate-digest-pending-new.txt"
GATE_DIGEST_INSERT_OLD_FILE = "gate-digest-insert-old.txt"
GATE_DIGEST_INSERT_NEW_FILE = "gate-digest-insert-new.txt"
GATE_FINAL_HELPERS_OLD_FILE = "gate-final-helpers-old.txt"
GATE_FINAL_HELPERS_NEW_FILE = "gate-final-helpers-new.txt"
GATE_FINAL_PENDING_OLD_FILE = "gate-final-pending-old.txt"
GATE_FINAL_PENDING_NEW_FILE = "gate-final-pending-new.txt"

#: The line the two guard helpers are inserted in front of. `check()` is
#: defined once in `jarvis_gate.py`; the tool refuses if that is not true in
#: the live file.
GATE_GUARDS_CHECK_ANCHOR = "def check(action: str,"

#: The data-driven HUD-delta table. Each entry says, for one patch and one patched file:
#:   probes: distinctive post-image lines; ALL must be in the live file to count as present
#:   anchor: the exact line the patch's added lines are inserted BEFORE (must appear once)
#:   file:   a literal block (a fix with no `.patch`), inserted at `anchor`
#:   replace_file: a literal block that REPLACES the named old block (must appear once)
#: A patch touching a patched file that is absent and has no entry here is refused, not
#: guessed. Adding a new HUD patch is one small entry, not new code.
DELTA_TABLE = {
    "app-control.patch": {
        "jarvis_hud.py": {
            "probes": ('"/api/app-control/run"', '"/api/app-control/step"'),
            "anchor": APP_CONTROL_ANCHOR,
        },
    },
    "setup.patch": {
        "jarvis_hud.py": {
            "probes": ("/api/setup", "jarvis_setup.install("),
            "anchor": PLUGIN_LOADER_MARKER,
        },
    },
    "plugin-loader.patch": {
        "jarvis_hud.py": {
            "probes": ("plugin-loader.patch (this branch)", "jarvis_plugins.install("),
            "anchor": BEFORE_SOCKET,
        },
    },
    # The HUD fixes that no .patch carries: literal, and a REPLACE entry's old
    # block must appear in the live file exactly once (a half-applied deploy is
    # refused, never guessed at).
    "hud-status-cache.patch": {
        "jarvis_hud.py": {
            "probes": ("_status_poller_daemon", "_STATUS_POLL_SECONDS"),
            "anchor": STATUS_CACHE_ANCHOR,
            "file": STATUS_CACHE_FILE,
        },
    },
    "hud-status-poll-start.patch": {
        "jarvis_hud.py": {
            "probes": ("    _status_start_poller()",),
            "anchor": STATUS_START_ANCHOR,
            "file": STATUS_START_FILE,
        },
    },
    "hud-reasoning-fallback.patch": {
        "jarvis_hud.py": {
            "probes": ("CloudAnswer", "reasoning-fallback"),
            "file": REASONING_NEW_FILE,
            "replace_file": REASONING_OLD_FILE,
        },
    },
    # DEF-002's route half: the base's cached route REPLACES the live inline one.
    # Probes are two post-image lines that only the new route contains, so an
    # inline live route cannot be mistaken for present.
    "hud-status-route.patch": {
        "jarvis_hud.py": {
            "probes": ("if force or not _STATUS_CACHE:",
                       "force = (parse_qs(urlparse(self.path).query)"),
            "file": STATUS_ROUTE_NEW_FILE,
            "replace_file": STATUS_ROUTE_OLD_FILE,
        },
    },
    # Review ruling 8.2 (PR #680): the guard change is carried to the live
    # jarvis_gate.py as four literal deltas, ONE PER DISJOINT REGION - the
    # hashlib import, the two guard helpers before check(), the dedup ask
    # branch, and the `replaces` flag pending() puts on every waiting row.
    # EACH has two distinctive post-image probes, so a half-applied live
    # file can never be mistaken for a complete one; every old block must
    # appear exactly once in the live file or the deploy is refused.
    "gate-guards-import.patch": {
        "jarvis_gate.py": {
            "probes": ("import hashlib",),
            "file": GATE_GUARDS_IMPORT_NEW_FILE,
            "replace_file": GATE_GUARDS_IMPORT_OLD_FILE,
        },
    },
    "gate-guards-helpers.patch": {
        "jarvis_gate.py": {
            "probes": ("def _pending_target(", "def _pending_card_id("),
            "anchor": GATE_GUARDS_CHECK_ANCHOR,
            "file": GATE_GUARDS_HELPERS_NEW_FILE,
        },
    },
    "gate-guards-dedup.patch": {
        "jarvis_gate.py": {
            "probes": ("_pending_card_id(c, action, detail, prompt)",
                       "BEGIN IMMEDIATE"),
            "file": GATE_GUARDS_DEDUP_NEW_FILE,
            "replace_file": GATE_GUARDS_DEDUP_OLD_FILE,
        },
    },
    "gate-guards-replaces.patch": {
        "jarvis_gate.py": {
            "probes": ('d["replaces"] = replaces_for(',),
            "file": GATE_GUARDS_REPLACES_NEW_FILE,
            "replace_file": GATE_GUARDS_REPLACES_OLD_FILE,
        },
    },
    # F-680-2 (2026-10-21 pre-merge audit): the long-detail dedupe fix as THREE
    # literal deltas over the POST-#688 gate the four guard entries above leave
    # behind. Order matters: the old blocks exist only after those entries have
    # been applied to the staged text, so these sit after them in this dict.
    # EACH carries post-image probes, so a second deploy sees them as ALREADY
    # and a half-applied gate is refused (old block not exactly once), never
    # guessed at.
    "gate-digest-init.patch": {
        "jarvis_gate.py": {
            "probes": ("ADD COLUMN target_digest TEXT",),
            "file": GATE_DIGEST_INIT_NEW_FILE,
            "replace_file": GATE_DIGEST_INIT_OLD_FILE,
        },
    },
    "gate-digest-pending.patch": {
        "jarvis_gate.py": {
            "probes": ('"SELECT id, detail, prompt, target_digest FROM approvals"',
                       "if stored_digest:"),
            "file": GATE_DIGEST_PENDING_NEW_FILE,
            "replace_file": GATE_DIGEST_PENDING_OLD_FILE,
        },
    },
    "gate-digest-insert.patch": {
        "jarvis_gate.py": {
            "probes": ("created,raised,target_digest)",),
            "file": GATE_DIGEST_INSERT_NEW_FILE,
            "replace_file": GATE_DIGEST_INSERT_OLD_FILE,
        },
    },
    # The extended two-press set (#688) and review ruling 8.1's three accurate
    # labels, carried to the live gate in the SAME PR that changes it (Ruling
    # 8.2's standing rule). TWO literal deltas over what the entries above leave
    # behind: the guard entries are already present on this PC, so the digest
    # entries rewrite the old four-action text, and these two then bring the
    # live gate to the published text - the ten-action set, the kind/heading/
    # note payload and the digest-aware dedupe function in one helpers block.
    # OLD blocks were taken from `9cfe49920`'s carried blocks (what the #687
    # deploy wrote) with the digest function substituted, i.e. exactly the
    # staged text at this point in the order; NEW blocks are the published
    # gate's own text. Post-image probes make a second deploy ALREADY_PRESENT.
    "gate-final-helpers.patch": {
        "jarvis_gate.py": {
            "probes": ("_REPLACES_KINDS = {",
                       "def replaces_kind_for(action, detail=None):"),
            "file": GATE_FINAL_HELPERS_NEW_FILE,
            "replace_file": GATE_FINAL_HELPERS_OLD_FILE,
        },
    },
    "gate-final-pending.patch": {
        "jarvis_gate.py": {
            "probes": ('d["replaces_kind"] = _kinds.get("kind")',
                       'd["replaces_note"] = _kinds.get("note", "")'),
            "file": GATE_FINAL_PENDING_NEW_FILE,
            "replace_file": GATE_FINAL_PENDING_OLD_FILE,
        },
    },
}

#: Live-HUD deltas that are RECORDED BUT DELIBERATELY NOT APPLIED. They are kept
#: as data so the decision is visible, testable and not lost; run_deploy prints
#: them and never stages them. A blocked entry is NOT a small patch waiting for
#: an anchor - it is the evidence that no safe anchor exists today.
#:
#: F10 / Gemini Q2 ruling (2026-10-20): traces.db retention was to be a live-HUD
#: delta, not a fake backend module. The live HUD was read read-only and has no
#: traces.db writer, no schema and no insert/startup anchor for it (evidence in
#: the entry). Adding a startup prune anyway would delete a database this
#: program does not own, so the honest result is BLOCKED, not a guess.
BLOCKED_DELTAS = {
    "traces-retention": {
        "file": "jarvis_hud.py",
        "why": ("the live jarvis_hud.py has no traces.db writer, no trace schema "
                "and no insert/startup anchor to attach a retention cap to; a "
                "standalone prune would delete a database this program does not "
                "own, so nothing is staged or applied"),
        "evidence": (
            "live jarvis_hud.py (2026-10-20, 393,012 bytes): zero 'traces.db' "
            "matches; sqlite3 is imported only for the read-only memory readers "
            "(around lines 6238-6265); CONFIG_DIR is at :81. No live module in "
            "the Desktop program folder writes traces.db.",
            "the live config folder (~/.openjarvis) has no traces.db today, and "
            "the live folder has no traces.db writer or reader to anchor to.",
            "the last evidence of the store is a snapshot, not live code: "
            "Jarvis Backups/jarvis-snap-20261014-000438/traces.db (36,864 B) has "
            "tables traces(id, trace_id, query, result, agent, started_at, "
            "ended_at, ...), trace_steps(trace_id, timestamp, ...) and an FTS5 "
            "traces_fts with only an INSERT trigger (traces_fts_ai), no delete "
            "trigger; the repository names traces.db only in "
            "backend/jarvis_backup.py:470/487.",
            "therefore a delta cannot reuse the HUD's anchored ALREADY_PRESENT/"
            "insert mechanism for this store: there is no post-image line to "
            "probe and no insert to anchor to.",
        ),
    },
}


def blocked_delta_lines() -> list:
    """Plain one-line summaries of BLOCKED_DELTAS, for the dry-run summary.

    These are REPORTED, never staged: the deploy summary says BLOCKED and the
    exit code is not changed by them (they are not a failed required step)."""
    out = []
    for name, entry in sorted(BLOCKED_DELTAS.items()):
        out.append(f"{name} -> {entry.get('file', '')}: "
                   f"{entry.get('why', 'recorded blocked')}")
    return out


#: Lines too generic to prove a patch is present.
_GENERIC_PROBES = frozenset({
    "try:", "except Exception:", "except Exception as exc:", "pass", "return True",
    "return False", "import os", "import sys", "import json", "else:", "endif",
})

#: A file that must never be sourced from the base folder (stale snapshot).
_NEVER_FROM_BASE = ("jarvis-backend/",)

BACKUP_PREFIX = "_jarvis-deploy-backup-tool-"
JOURNAL_NAME = "_journal.json"

CLIENT_HEADER = "X-Jarvis-Client"
TOKEN_HEADER = "X-Jarvis-Token"
CLIENT_VALUE = "hud"


class Refused(Exception):
    """The deploy will not start or will not continue; nothing has been written."""


@dataclass
class ShippedAction:
    repo_path: str          # e.g. "rebuilt/jarvis_compute.py"
    live_name: str          # e.g. "jarvis_compute.py"
    status: str             # "add" | "update" | "unchanged"
    blob: Optional[bytes] = None


@dataclass
class DeltaAction:
    patch: str
    file: str
    status: str             # "already" | "insert"
    lines: tuple = ()
    anchor: str = ""


@dataclass
class Plan:
    shipped: list = field(default_factory=list)
    deltas: list = field(default_factory=list)
    staged: dict = field(default_factory=dict)   # file -> new text, only for changed files
    refusals: list = field(default_factory=list)
    pycache: list = field(default_factory=list)
    plugins_missing: list = field(default_factory=list)
    plugins_present: list = field(default_factory=list)
    plugins_wired: list = field(default_factory=list)
    broken_plugins: list = field(default_factory=list)


# ---------------------------------------------------------------------------
#   Reading the authoritative lists out of apply-patches.ps1
# ---------------------------------------------------------------------------

_LIST_START = re.compile(r"^\s*\$([A-Za-z_][A-Za-z0-9_]*)\s*=\s*@\(\s*$")
_QUOTED = re.compile(r"""^\s*['"]([^'"]+)['"]""")


def parse_powershell_list(text: str, variable: str) -> list:
    """The quoted first item of every non-comment line of `$<variable> = @( ... )`.

    This is the same extraction apply-patches.ps1's own `$SHIPPED` consumers use: one
    quoted file name per line, comments and blank lines ignored, a trailing comment
    after the quote ignored. It refuses a variable that is not there or an unterminated
    block, because silently reading an empty list would skip the whole sync."""
    marker = f"${variable} = @("
    start = text.find(marker)
    if start < 0:
        raise Refused(f"scripts/apply-patches.ps1 has no ${variable} = @( block")
    start += len(marker)
    end = text.find("\n)", start)
    if end < 0:
        raise Refused(f"the ${variable} list is not closed with a line containing only ')'")
    out = []
    for line in text[start:end].splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        match = _QUOTED.match(s)
        if match:
            out.append(match.group(1))
    if not out:
        raise Refused(f"the ${variable} list parsed as empty")
    return out


def read_patch_lists(repo: Path) -> tuple:
    script = Path(repo) / "scripts" / "apply-patches.ps1"
    if not script.is_file():
        raise Refused(f"no scripts/apply-patches.ps1 under {repo}")
    text = script.read_text(encoding="utf-8")
    return parse_powershell_list(text, "SHIPPED"), parse_powershell_list(text, "PATCHES")


def flatten_shipped(entries: Iterable[str]) -> list:
    """[(repo_path, live_name)] for the $SHIPPED entries.

    `rebuilt/<name>` lands as `<name>` beside jarvis_hud.py on the live PC. Every other
    entry is already a bare name. Absolute paths, `..` and duplicates are refused."""
    out = []
    seen = set()
    for entry in entries:
        repo_path = str(entry).replace("\\", "/")
        if repo_path.startswith(_NEVER_FROM_BASE):
            raise Refused(f"the $SHIPPED list names {repo_path!r}; the base folder must "
                          f"never be deployed over live")
        posix = PurePosixPath(repo_path)
        if (repo_path.startswith("/") or ":" in repo_path or posix.is_absolute()
                or ".." in posix.parts or not posix.name):
            raise Refused(f"the $SHIPPED entry {entry!r} is not a safe relative path")
        live_name = posix.name
        if live_name in seen:
            raise Refused(f"the $SHIPPED list names {live_name!r} twice")
        seen.add(live_name)
        out.append((repo_path, live_name))
    return out


# ---------------------------------------------------------------------------
#   Git and the shipped-byte comparison
# ---------------------------------------------------------------------------

def git_show(repo: Path, ref: str, repo_path: str) -> bytes:
    """`git show <ref>:backend/<repo_path>` as bytes - the exact blob, no checkout."""
    full = f"{ref}:backend/{repo_path}"
    try:
        proc = subprocess.run(["git", "-C", str(repo), "show", full],
                              capture_output=True, timeout=120)
    except Exception as exc:                                  # noqa: BLE001
        raise Refused(f"could not run git show {full} ({type(exc).__name__})") from exc
    if proc.returncode != 0:
        msg = (proc.stderr or b"").decode("utf-8", "replace").strip()
        raise Refused(f"git show {full} failed: {msg or 'no such blob'}")
    return proc.stdout


def plan_shipped(repo: Path, ref: str, live: Path, shipped: list,
                 show: Optional[Callable] = None) -> list:
    """Compare every shipped file's bytes with the ref; copy only changed/missing."""
    show = show or git_show
    actions = []
    for repo_path, live_name in flatten_shipped(shipped):
        blob = show(repo, ref, repo_path)
        target = Path(live) / live_name
        if not target.is_file():
            actions.append(ShippedAction(repo_path, live_name, "add", blob))
            continue
        current = target.read_bytes()
        status = "unchanged" if current == blob else "update"
        actions.append(ShippedAction(repo_path, live_name, status, blob))
    return actions


# ---------------------------------------------------------------------------
#   Unified-diff parsing and the HUD-delta decision
# ---------------------------------------------------------------------------

_FILE_HEADER = re.compile(r"^--- a/(\S+)\s*$")


def parse_patch_files(patch_text: str) -> dict:
    """{file: {"added": [...], "removed": [...]}} from one unified diff.

    Only `+`/`-` body lines are collected (the `+++ b/...` and `--- a/...` headers are
    not body lines). A patch that touches several files is handled section by section."""
    files = {}
    current = None
    for line in str(patch_text).splitlines():
        header = _FILE_HEADER.match(line)
        if header:
            current = header.group(1)
            files.setdefault(current, {"added": [], "removed": []})
            continue
        if current is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            files[current]["added"].append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            files[current]["removed"].append(line[1:])
    return files


def probe_candidates(added: Iterable[str], limit: int = 3) -> tuple:
    """The most distinctive added lines of one patch/file, best first.

    A line is distinctive when it is long enough to mean something and is not one of the
    generic Python shapes every patch contains. Routes and install() calls rank highest."""
    scored = []
    seen = set()
    for raw in added:
        s = str(raw).strip()
        if len(s) < 12 or s in _GENERIC_PROBES or s in seen:
            continue
        seen.add(s)
        score = 0
        if "/api/" in s:
            score += 4
        if "install(" in s:
            score += 3
        if s.startswith(("def ", "class ")):
            score += 2
        if '"' in s or "'" in s:
            score += 1
        score += min(len(s), 120) / 200.0
        scored.append((score, s))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return tuple(s for _score, s in scored[:limit])


def patch_present(patch: str, target: str, added: Iterable[str], live_text: str,
                  table: Optional[dict] = None,
                  state_patches: Optional[Iterable[str]] = None) -> bool:
    """Is this patch's delta already in the live file?

    Table entries carry their own distinctive probes and ALL must be present (so a
    half-inserted block is not mistaken for present). Other patches use their most
    distinctive added lines - any one is enough, because later patches legitimately
    rewrite neighbouring lines. When the lines cannot prove anything (a very old patch
    later rewritten), the live `_jarvis-state.json` patch list is the honest fallback."""
    table = DELTA_TABLE if table is None else table
    entry = ((table.get(patch) or {}).get(target) or {})
    probes = tuple(entry.get("probes") or ())
    if probes:
        return all(str(p) in live_text for p in probes)
    candidates = probe_candidates(added)
    if candidates and any(c in live_text for c in candidates):
        return True
    # A patch applied long ago can have its added lines rewritten by later patches, so
    # its text may no longer survive. The live deploy's own patch list is the fallback
    # evidence: if the PC recorded that patch as applied, it is not missing again.
    state = {str(s).replace("\\", "/").split("/")[-1] for s in (state_patches or ())}
    return patch.split("/")[-1] in state


def insert_before_anchor(text: str, block_lines: Iterable[str], anchor: str,
                         *, where: str = "") -> str:
    """Insert one patch's added lines immediately before `anchor`, exactly once.

    The anchor must appear exactly once; zero or several occurrences is a refusal (a
    deploy that guesses is how a route lands in the wrong dispatch chain). The block
    keeps the patch's own bytes and gets a newline before it if the file lacks one."""
    anchor = str(anchor)
    if not anchor:
        raise Refused(f"{where}: no anchor text is configured")
    count = text.count(anchor)
    if count != 1:
        raise Refused(f"{where}: the anchor {anchor!r} appears {count} time(s) in the "
                      f"live file; expected exactly 1. Refusing rather than guessing.")
    block = "\n".join(str(l) for l in block_lines) + "\n"
    at = text.index(anchor)
    prefix = text[:at]
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    return prefix + block + text[at:]


def _live_state_patches(live: Path) -> list:
    state = Path(live) / "_jarvis-state.json"
    try:
        doc = json.loads(state.read_text(encoding="utf-8"))
        items = doc.get("patchList") or []
        return [str(i if isinstance(i, str) else (i or {}).get("name") or "")
                for i in items if i]
    except Exception:                                         # noqa: BLE001
        return []


def plan_deltas(live: Path, patches: Iterable[str], *,
                show: Optional[Callable] = None, repo: Optional[Path] = None,
                ref: str = "origin/main", table: Optional[dict] = None,
                state_patches: Optional[Iterable[str]] = None,
                literals: bool = False) -> tuple:
    """(deltas, staged_texts, refusals) for the five patched files. Reads only.

    `show(repo, ref, "<patch>")` supplies the patch text (tests inject it).
    The staged_texts dict holds a new copy for each changed file; nothing is written."""
    show = show or git_show
    repo = Path(repo) if repo is not None else Path(__file__).resolve().parent.parent
    table = DELTA_TABLE if table is None else table
    state = list(state_patches) if state_patches is not None else _live_state_patches(live)
    live_text = {}
    staged = {}
    for name in PATCHED_FILES:
        path = Path(live) / name
        if path.is_file():
            live_text[name] = path.read_text(encoding="utf-8", errors="surrogateescape")
        else:
            live_text[name] = ""
            staged[name] = ""       # recorded so a "missing patched file" is seen below

    deltas = []
    refusals = []
    missing_files = [n for n in PATCHED_FILES if not (Path(live) / n).is_file()]
    if missing_files:
        refusals.append("the live folder has no " + ", ".join(missing_files))
        return deltas, staged, refusals

    for patch in patches:
        raw = show(repo, ref, patch)          # patch text lives at backend/<patch>
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        files = parse_patch_files(raw)
        for target in PATCHED_FILES:
            added = (files.get(target) or {}).get("added") or []
            if not added:
                continue
            text = staged.get(target) or live_text[target]
            if patch_present(patch, target, added, text, table=table, state_patches=state):
                deltas.append(DeltaAction(patch, target, "already"))
                continue
            entry = (table.get(patch) or {}).get(target) or {}
            anchor = entry.get("anchor") or ""
            if not anchor:
                refusals.append(
                    f"{patch} touches {target} and is not present, but there is no "
                    f"insertion rule for it. Add one to DELTA_TABLE (anchor + probes) "
                    f"after reading the patch; refusing to guess.")
                continue
            try:
                text = insert_before_anchor(text, added, anchor,
                                            where=f"{patch} -> {target}")
            except Refused as exc:
                refusals.append(str(exc))
                continue
            if text != (staged.get(target) or live_text[target]):
                staged[target] = text
                deltas.append(DeltaAction(patch, target, "insert", tuple(added), anchor))
    # Literal deltas: fixes that have no .patch of their own - the 2026-10-14
    # HUD fixes, and review ruling 8.2's guard change carried to jarvis_gate.py
    # (see DELTA_TABLE). They are processed after the stack so their anchors see
    # the same staged text, and only when the pick was not already made by a
    # patch of the same name. ANY of the five patched files may be named: a
    # literal entry is ONE block in ONE file, which is what keeps a change
    # touching two base files from needing new code (the HUD entries behave
    # exactly as they did before this loop was generalised).
    known = set(patches)
    literal_items = list(table.items()) if literals else ()
    for patch, targets in literal_items:
        if patch in known:
            continue
        for target, entry in targets.items():
            if target not in PATCHED_FILES:
                refusals.append(
                    f"{patch} -> {target}: a literal delta must name one of the "
                    f"five patched base files ({', '.join(PATCHED_FILES)}); "
                    f"refusing to guess.")
                continue
            lines = tuple(entry.get("lines") or ())
            if not lines and entry.get("file"):
                try:
                    lines = _delta_lines(str(entry["file"]))
                except Exception as exc:                      # noqa: BLE001
                    refusals.append(f"{patch} -> {target}: its block file could "
                                    f"not be read ({type(exc).__name__})")
                    continue
            if not lines:
                continue
            text = staged.get(target) or live_text.get(target, "")
            if patch_present(patch, target, (), text, table=table,
                             state_patches=state):
                deltas.append(DeltaAction(patch, target, "already"))
                continue
            old = str(entry.get("replace") or "")
            if not old and entry.get("replace_file"):
                try:
                    old = "\n".join(_delta_lines(str(entry["replace_file"])))
                except Exception as exc:                      # noqa: BLE001
                    refusals.append(f"{patch} -> {target}: its old block file "
                                    f"could not be read ({type(exc).__name__})")
                    continue
            try:
                if old:
                    count = text.count(old)
                    if count != 1:
                        raise Refused(
                            f"{patch} -> {target}: its old block appears "
                            f"{count} time(s) in the live file; expected exactly 1. "
                            f"Refusing rather than guessing.")
                    text = text.replace(old, "\n".join(lines), 1)
                else:
                    text = insert_before_anchor(text, lines, entry.get("anchor") or "",
                                                where=f"{patch} -> {target}")
            except Refused as exc:
                refusals.append(str(exc))
                continue
            if text != (staged.get(target) or live_text.get(target, "")):
                staged[target] = text
                deltas.append(DeltaAction(patch, target, "insert", tuple(lines),
                                          str(entry.get("anchor")
                                              or entry.get("replace_file") or "")))
    # Only files that really changed need staging/swapping.
    staged = {name: text for name, text in staged.items()
              if text != live_text.get(name, "")}
    if refusals:
        return deltas, {}, refusals
    return deltas, staged, []


# ---------------------------------------------------------------------------
#   Rehearsal, backup and writing
# ---------------------------------------------------------------------------

def rehearse(staged: dict) -> list:
    """Compile every staged Python file with py_compile. Returns plain error sentences."""
    errors = []
    if not staged:
        return errors
    tmp = Path(tempfile.mkdtemp(prefix="reconcile-rehearsal-"))
    try:
        for name, text in sorted(staged.items()):
            if not name.endswith(".py"):
                continue
            path = tmp / name
            path.write_text(text, encoding="utf-8", errors="surrogateescape")
            try:
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as exc:
                errors.append(f"{name}: {exc.msg}")
            except Exception as exc:                          # noqa: BLE001
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return errors


def _restore_entries(live: Path, root: Path, entries: list) -> tuple:
    """Restore one journal's entries, newest first. Returns (restored, removed, failures).

    The journal is the failure half of the deploy: every overwritten file has a
    copy under `backup_root`, every newly created file/dir has `existed: false`,
    and the live path is re-checked to stay under the live folder. A failed
    restore is reported per path; it never raises into the caller's report.
    """
    live = Path(live).resolve()
    root = Path(root)
    restored = removed = 0
    failures = []
    for entry in reversed(list(entries or [])):
        rel = str(entry.get("path") or "")
        try:
            target = (live / rel).resolve()
            if target != live and live not in target.parents:
                raise ValueError("journal path leaves the live folder")
            if entry.get("existed"):
                backup_rel = str(entry.get("backup") or "")
                if not backup_rel:
                    raise ValueError("journal entry has no backup copy")
                src = (root / backup_rel).resolve()
                if root.resolve() not in src.parents and src != root.resolve():
                    raise ValueError("journal backup path leaves the backup folder")
                if not src.exists():
                    raise FileNotFoundError(f"backup copy is missing: {backup_rel}")
                target.parent.mkdir(parents=True, exist_ok=True)
                if entry.get("kind") == "dir":
                    shutil.copytree(src, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, target)
                restored += 1
            else:
                if target.exists():
                    if entry.get("kind") == "dir":
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                    removed += 1
        except (OSError, ValueError) as exc:
            failures.append(f"{rel}: {exc}")
    return restored, removed, failures


def load_journal(backup_root: Path) -> dict:
    """Read one deploy journal. Raises Refused on anything unsafe or unreadable."""
    path = Path(backup_root) / JOURNAL_NAME
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Refused(f"cannot read the deploy journal {path}: {exc}") from exc
    except ValueError as exc:
        raise Refused(f"the deploy journal {path} is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("version") != 1 \
            or not isinstance(doc.get("entries"), list):
        raise Refused(f"{path} is not a version-1 deploy journal")
    return doc


def rollback_backup(live: Path, backup_root: Path, out: Optional[Callable] = None) -> int:
    """Restore a finished/partial deploy from its journal. No live write planning."""
    out = out or print
    doc = load_journal(backup_root)
    expected = str(Path(doc.get("live") or ""))
    if expected and Path(expected).resolve() != Path(live).resolve():
        out(f"REFUSED: the journal was written for {expected}, not {Path(live).resolve()}")
        return 2
    restored, removed, failures = _restore_entries(live, Path(backup_root), doc["entries"])
    out(f"ROLLBACK: restored {restored} overwritten path(s), removed {removed} new path(s)")
    for failure in failures:
        out(f"FAIL  {failure}")
    if failures:
        out(f"ROLLBACK INCOMPLETE - {len(failures)} path(s) need attention; the backup "
            f"folder is still at {Path(backup_root)}")
        return 1
    out(f"ROLLBACK OK - the live folder is back to its pre-deploy state; journal at "
        f"{Path(backup_root) / JOURNAL_NAME}")
    return 0


class Backup:
    """One timestamped folder under the live backend: every overwritten byte kept,
    and a journal that can put the live folder back after a failed write.

    `start()` is called before the first live write (the deploy prints it); a
    direct `save()` still works for the unit tests and creates the folder lazily.
    """

    def __init__(self, live: Path, stamp: Optional[str] = None):
        self.live = Path(live)
        stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
        self.root = self.live / f"{BACKUP_PREFIX}{stamp}"
        self.saved = []
        self.entries = []
        self.journal = self.root / JOURNAL_NAME
        self.started = False

    def start(self) -> Path:
        """Create the backup folder and an empty journal BEFORE any live write."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.started = True
        self._flush()
        return self.root

    def _rel(self, path: Path) -> str:
        return Path(path).relative_to(self.live).as_posix()

    def _flush(self) -> None:
        if not self.started:
            self.root.mkdir(parents=True, exist_ok=True)
            self.started = True
        doc = {"version": 1, "live": str(self.live.resolve()), "entries": self.entries}
        tmp = self.journal.with_name(self.journal.name + ".tmp")
        tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.journal)

    def _remember(self, entry: dict) -> None:
        self.entries.append(entry)
        self._flush()

    def save(self, path: Path) -> Path:
        path = Path(path)
        rel = self._rel(path)
        dest = self.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        if rel not in self.saved:
            self.saved.append(rel)
        if not any(e.get("path") == rel and e.get("backup") for e in self.entries):
            self._remember({"path": rel, "existed": True, "backup": rel, "kind": "file"})
        return dest

    def save_dir(self, path: Path) -> Path:
        """Back up an existing directory before a plugin step overwrites/adds inside it."""
        path = Path(path)
        rel = self._rel(path)
        dest = self.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(path, dest, dirs_exist_ok=True)
        if rel not in self.saved:
            self.saved.append(rel)
        self._remember({"path": rel, "existed": True, "backup": rel, "kind": "dir"})
        return dest

    def record_new(self, target: Path, *, directory: bool = False) -> None:
        """Record a path this run will CREATE (rollback removes it)."""
        rel = self._rel(target)
        if any(e.get("path") == rel for e in self.entries):
            return
        self._remember({"path": rel, "existed": False, "backup": None,
                        "kind": "dir" if directory else "file"})

    def rollback(self, out: Optional[Callable] = None) -> int:
        out = out or print
        restored, removed, failures = _restore_entries(self.live, self.root, self.entries)
        out(f"ROLLBACK: restored {restored} overwritten path(s), removed {removed} new path(s)")
        for failure in failures:
            out(f"FAIL  {failure}")
        if failures:
            out(f"ROLLBACK INCOMPLETE - the backup folder is {self.root}")
            return 1
        return 0


def apply_shipped(actions: Iterable[ShippedAction], live: Path,
                  backup: Backup, *, write: bool = True) -> tuple:
    """Write the add/update actions (bytes exact). Returns (written, names)."""
    written = []
    for action in actions:
        if action.status == "unchanged":
            continue
        target = Path(live) / action.live_name
        if not write:
            written.append(action.live_name)
            continue
        if target.exists():
            backup.save(target)          # back up what is being overwritten
        else:
            backup.record_new(target)    # a failed later step removes this file
        target.write_bytes(action.blob or b"")
        written.append(action.live_name)
    return written


def apply_deltas(staged: dict, live: Path, backup: Backup, *, write: bool = True) -> list:
    written = []
    for name, text in sorted(staged.items()):
        target = Path(live) / name
        if not write:
            written.append(name)
            continue
        backup.save(target)
        target.write_text(text, encoding="utf-8", errors="surrogateescape", newline="")
        written.append(name)
    return written


# ---------------------------------------------------------------------------
#   Pycache purge
# ---------------------------------------------------------------------------

def plan_pycache(live: Path) -> list:
    folder = Path(live) / "__pycache__"
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.pyc"))


def purge_pycache(live: Path, backup: Optional["Backup"] = None) -> list:
    deleted = []
    for path in plan_pycache(live):
        try:
            if backup is not None:
                backup.save(path)        # a rollback restores the bytecode too
            path.unlink()
            deleted.append(path.name)
        except OSError:
            pass
    return deleted


# ---------------------------------------------------------------------------
#   Ready plug-ins
# ---------------------------------------------------------------------------

def ready_plugins(repo: Path) -> tuple:
    """([names], [broken]) for plugins/ready/<name>/plugin.json; never raises."""
    root = Path(repo) / "plugins" / "ready"
    names, broken = [], []
    if not root.is_dir():
        return names, broken
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        manifest = child / "plugin.json"
        if not manifest.is_file():
            continue
        try:
            doc = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:                              # noqa: BLE001
            broken.append(f"{child.name}: plugin.json will not parse ({type(exc).__name__})")
            continue
        if not isinstance(doc, dict) or not doc.get("module"):
            broken.append(f"{child.name}: plugin.json names no module")
            continue
        names.append(str(doc.get("name") or child.name))
    return names, broken


def plan_plugins(live: Path, repo: Path) -> tuple:
    """(missing, present, broken, hud_wired). `hud_wired` is the safety guard.

    A ready folder is skipped when the live HUD already calls `<module>.install(...)`:
    the patch stack wired that feature, and letting jarvis_plugins.install() call the
    same module a second time would double-wire it for no gain."""
    names, broken = ready_plugins(repo)
    present, hud_wired = [], []
    live_hud = ""
    try:
        live_hud = (Path(live) / "jarvis_hud.py").read_text(encoding="utf-8",
                                                            errors="surrogateescape")
    except Exception:                                         # noqa: BLE001
        live_hud = ""
    manifest_module = {}
    for name in names:
        manifest = Path(repo) / "plugins" / "ready" / name / "plugin.json"
        try:
            manifest_module[name] = str(json.loads(
                manifest.read_text(encoding="utf-8")).get("module") or "")
        except Exception:                                     # noqa: BLE001
            manifest_module[name] = ""
        if (Path(live) / "jarvis_plugins" / name).is_dir():
            present.append(name)
        elif manifest_module[name] and f"{manifest_module[name]}.install(" in live_hud:
            hud_wired.append(name)
    missing = [n for n in names if n not in present and n not in hud_wired]
    return missing, present, broken, hud_wired


def _powershell() -> str:
    for exe in ("powershell", "powershell.exe", "pwsh", "pwsh.exe"):
        found = shutil.which(exe)
        if found:
            return found
    return ""


def add_plugin(repo: Path, live: Path, name: str,
               runner: Optional[Callable] = None) -> tuple:
    """Run scripts/add-plugin.ps1 for one ready plug-in. Returns (ok, one-line why)."""
    runner = runner or (lambda argv, cwd=None: subprocess.run(
        argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=180))
    exe = _powershell()
    if not exe:
        return False, "no PowerShell found (scripts/add-plugin.ps1 needs it)"
    script = Path(repo) / "scripts" / "add-plugin.ps1"
    if not script.is_file():
        return False, "scripts/add-plugin.ps1 is not in this repository"
    argv = [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(script), "-BackendPath", str(live), "-Name", name]
    try:
        proc = runner(argv, cwd=repo)
    except Exception as exc:                                  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    out = ((getattr(proc, "stdout", "") or "") + (getattr(proc, "stderr", "") or "")).strip()
    last = out.splitlines()[-1].strip() if out else ""
    ok = int(getattr(proc, "returncode", 1) or 0) == 0 and "SKIP" not in out.upper() \
        and "FAIL" not in out.upper()
    return ok, last or f"exit {getattr(proc, 'returncode', '?')}"


# ---------------------------------------------------------------------------
#   Route probes (read-only; the token is never printed)
# ---------------------------------------------------------------------------

class ProbeError(Exception):
    pass


def read_token(live: Path, runner: Optional[Callable] = None) -> str:
    """`python jarvis_token_store.py show` in the live folder. Never printed or logged."""
    runner = runner or (lambda argv, cwd=None: subprocess.run(
        argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=30))
    script = Path(live) / "jarvis_token_store.py"
    if not script.is_file():
        raise ProbeError("jarvis_token_store.py is not in the live folder")
    try:
        proc = runner([sys.executable or "python", "jarvis_token_store.py", "show"],
                      cwd=live)
    except Exception as exc:                                  # noqa: BLE001
        raise ProbeError(f"could not read the token ({type(exc).__name__})") from exc
    if int(getattr(proc, "returncode", 1) or 0) != 0:
        raise ProbeError("jarvis_token_store.py show did not succeed")
    token = (getattr(proc, "stdout", "") or "").strip()
    if not token:
        raise ProbeError("jarvis_token_store.py show printed no token")
    return token


def probe_http(url: str, method: str = "GET", body: Optional[dict] = None,
               token: str = "", timeout: float = 10.0) -> tuple:
    """(status, payload). Raises ProbeError only when no HTTP answer arrived."""
    import urllib.error
    import urllib.request
    data = None
    headers = {CLIENT_HEADER: CLIENT_VALUE, "Accept": "application/json"}
    if token:
        headers[TOKEN_HEADER] = token
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers,
                                     method=str(method).upper())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            raw = answer.read()
            status = int(answer.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = int(exc.code)
    except Exception as exc:                                  # noqa: BLE001
        raise ProbeError(f"no answer from {url} ({type(exc).__name__})") from exc
    try:
        payload = json.loads(raw.decode("utf-8", "replace") or "{}")
    except ValueError:
        payload = (raw or b"").decode("utf-8", "replace")
    return status, payload


def _hud_port(live: Path) -> int:
    try:
        text = (Path(live) / "jarvis_hud.py").read_text(encoding="utf-8",
                                                        errors="surrogateescape")
        match = re.search(r'JARVIS_HUD_PORT"\s*,\s*"(\d+)"', text)
        if match:
            return int(match.group(1))
    except Exception:                                         # noqa: BLE001
        pass
    return 4719


def _app_control_absent(live: Path) -> bool:
    try:
        text = (Path(live) / "jarvis-framework.toml").read_text(encoding="utf-8")
        return re.search(r"(?m)^\s*\[app_control\]\s*$", text) is None
    except Exception:                                         # noqa: BLE001
        return True


def run_probes(live: Path, base_url: str = "", *,
               client: Optional[Callable] = None,
               token_reader: Optional[Callable] = None,
               out: Optional[Callable] = None) -> int:
    """PASS/FAIL/SKIP per probe. Returns the number of FAILED expected probes."""
    client = client or probe_http
    token_reader = token_reader or read_token
    out = out or print
    base = (base_url or f"http://127.0.0.1:{_hud_port(live)}").rstrip("/")
    try:
        token = token_reader(live)
    except ProbeError as exc:
        out(f"FAIL  token: {exc}")
        return 1

    probes = []   # (name, method, path, body, expected status, extra check or None)
    probes.append(("setup", "GET", "/api/setup", None, 200, None))
    if (Path(live) / "jarvis_plugins" / "media-index").is_dir():
        probes.append(("media-index", "GET", "/api/media-index", None, 200, None))
    else:
        probes.append(("media-index", "", "", None, None,
                       "the media-index plug-in is not installed"))
    if _app_control_absent(live):
        probes.append(("app-control", "POST", "/api/app-control/run", {}, 409, None))
    else:
        probes.append(("app-control", "", "", None, None,
                       "[app_control] is present, so 409-when-off is not the expectation"))

    def voice_ok(payload) -> bool:
        return (isinstance(payload, dict) and isinstance(payload.get("gate"), dict)
                and "training" in payload["gate"])

    probes.append(("voice", "GET", "/api/voice/status", None, 200, voice_ok))

    failed = 0
    for name, method, path, body, expected, extra in probes:
        if not method:
            out(f"SKIP  {name}: {extra}")
            continue
        url = base + path
        try:
            status, payload = client(url, method, body, token)
        except ProbeError as exc:
            out(f"FAIL  {name}: {exc}")
            failed += 1
            continue
        ok = status == expected and (extra is None or extra(payload))
        detail = f"{method} {path} -> {status} (expected {expected})"
        if extra is not None and status == expected and not ok:
            detail += "; response shape did not match"
        out(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
        if not ok:
            failed += 1
    return failed


# ---------------------------------------------------------------------------
#   The deploy itself
# ---------------------------------------------------------------------------

def _summ(out, label, items, limit=12):
    if not items:
        out(f"  {label}: none")
        return
    out(f"  {label}: {len(items)}")
    for item in items[:limit]:
        out(f"      {item}")
    if len(items) > limit:
        out(f"      ... and {len(items) - limit} more")


def run_deploy(repo: Path, live: Path, *, apply: bool = False, ref: str = "origin/main",
               skip_plugins: bool = False, base_url: str = "",
               show: Optional[Callable] = None, out: Optional[Callable] = None,
               probe_client: Optional[Callable] = None,
               token_reader: Optional[Callable] = None,
               plugin_runner: Optional[Callable] = None,
               stamp: Optional[str] = None) -> int:
    out = out or print
    repo = Path(repo)
    live = Path(live)
    mode = "APPLY" if apply else "DRY RUN"
    out(f"Jarvis live-backend reconcile - {mode}")
    out(f"  repo: {repo}")
    out(f"  live: {live}")
    out(f"  ref : {ref}")
    out("")
    if not (live / "jarvis_hud.py").is_file():
        raise Refused(f"no jarvis_hud.py in {live} - is this the live backend folder?")
    if not (repo / "scripts" / "apply-patches.ps1").is_file():
        raise Refused(f"no scripts/apply-patches.ps1 under {repo}")
    if apply and not (repo / ".git").exists() and not (repo / ".git").is_file():
        raise Refused(f"{repo} is not a git repository")

    # 1. Plan the shipped sync.
    shipped, patches = read_patch_lists(repo)
    plan = Plan()
    try:
        plan.shipped = plan_shipped(repo, ref, live, shipped, show=show)
    except Refused as exc:
        out(f"REFUSED: {exc}")
        return 2
    adds = [a for a in plan.shipped if a.status == "add"]
    updates = [a for a in plan.shipped if a.status == "update"]
    unchanged = [a for a in plan.shipped if a.status == "unchanged"]
    out(f"SHIPPED ({len(plan.shipped)} files in $SHIPPED, flattened):")
    _summ(out, "to add", [a.live_name for a in adds])
    _summ(out, "to update", [a.live_name for a in updates])
    out(f"  unchanged: {len(unchanged)}")

    # 2. Plan the HUD deltas.
    try:
        deltas, staged, refusals = plan_deltas(live, patches, show=show, repo=repo,
                                               ref=ref, literals=True)
    except Refused as exc:
        out(f"REFUSED: {exc}")
        return 2
    plan.deltas = deltas
    plan.staged = staged
    if refusals:
        out("HUD DELTAS - REFUSED (nothing has been written):")
        _summ(out, "refusals", refusals, limit=20)
        return 2
    already = [d for d in deltas if d.status == "already"]
    inserts = [d for d in deltas if d.status == "insert"]
    out("")
    out(f"HUD DELTAS ({len(deltas)} patch/file delta(s) checked):")
    out(f"  already present: {len(already)}")
    _summ(out, "to insert", [f"{d.patch} -> {d.file} ({len(d.lines)} lines)" for d in inserts])
    blocked = blocked_delta_lines()
    if blocked:
        out("")
        out(f"BLOCKED LIVE DELTAS ({len(blocked)} recorded, NOT applied):")
        for line in blocked:
            out(f"  {line}")

    # 3. Rehearse before anything is swapped.
    errors = rehearse(staged)
    if errors:
        out("REHEARSAL FAILED (nothing has been written):")
        _summ(out, "errors", errors, limit=20)
        return 2
    if staged:
        out(f"  rehearsal: py_compile OK for {', '.join(sorted(staged))}")

    # 4. Pycache and plug-ins plans.
    plan.pycache = plan_pycache(live)
    out("")
    out(f"PYCACHE: {len(plan.pycache)} stale .pyc file(s)")
    if not skip_plugins:
        (plan.plugins_missing, plan.plugins_present, plan.broken_plugins,
         plan.plugins_wired) = plan_plugins(live, repo)
        out(f"READY PLUG-INS: {len(plan.plugins_present)} present, "
            f"{len(plan.plugins_missing)} to add, {len(plan.plugins_wired)} already "
            f"wired by the HUD")
        _summ(out, "to add", plan.plugins_missing)
        _summ(out, "skipped (the HUD already calls their install())", plan.plugins_wired)
        _summ(out, "broken manifests", plan.broken_plugins)
    else:
        out("READY PLUG-INS: skipped (--skip-plugins)")

    changes = len(adds) + len(updates) + len(inserts) + len(plan.pycache)
    out("")
    out(f"PLANNED CHANGES: {changes} file-level change(s)"
        + ("" if apply else " - DRY RUN, nothing written"))
    if not apply:
        out("Probes are not run in a dry run; use --apply after reviewing this plan.")
        return 0

    # 5. Write: shipped bytes, then the staged HUD files. The backup folder and
    # its journal are created and PRINTED before the first live write, so a
    # failure half-way through always has a named recovery point.
    has_writes = bool(adds or updates or inserts or plan.pycache
                      or (not skip_plugins and plan.plugins_missing))
    backup = Backup(live, stamp=stamp)
    written = []
    try:
        if has_writes:
            backup.start()
            out(f"BACKUP: {backup.root} (journal: {backup.journal.name})")
        else:
            out("BACKUP: nothing to overwrite or add; no backup folder needed")
        written += apply_shipped(plan.shipped, live, backup, write=True)
        written += apply_deltas(staged, live, backup, write=True)
    except OSError as exc:
        out(f"FAIL  writing the backend: {exc}")
        if has_writes:
            out(f"RESTORING from the backup printed above: {backup.root}")
            backup.rollback(out=out)
            out(f"RESULT: FAIL - the live folder was rolled back; the backup and "
                f"journal are at {backup.root}")
        else:
            out("RESULT: FAIL - nothing had been written yet")
        return 2

    # 6. Purge stale bytecode (backed up first when this is a real apply).
    purged = purge_pycache(live, backup if has_writes else None)
    out(f"PYCACHE: purged {len(purged)} stale .pyc file(s)")

    # 7. Ready plug-ins. A new folder is journaled before the step runs.
    plugin_failures = 0
    if not skip_plugins:
        for name in plan.plugins_missing:
            target = Path(live) / "jarvis_plugins" / name
            try:
                if target.exists():
                    backup.save_dir(target)
                else:
                    backup.record_new(target, directory=True)
            except OSError as exc:
                out(f"FAIL  plugin {name}: could not journal {target}: {exc}")
                plugin_failures += 1
                break
            ok, why = add_plugin(repo, live, name, runner=plugin_runner)
            out(f"{'PASS' if ok else 'FAIL'}  plugin {name}: {why}")
            if not ok:
                plugin_failures += 1
                break

    if plugin_failures:
        out("")
        out(f"RESTORING from the backup printed above: {backup.root}")
        backup.rollback(out=out)
        out(f"RESULT: FAIL - a ready plug-in could not be added; the live folder was "
            f"rolled back. Backup/journal: {backup.root}")
        return 1

    # 8. Route probes against the live server. The probe runs only after a
    # COMPLETE write; a probe failure keeps the new files and names the recovery
    # point instead of pretending the deploy is atomic with a running server.
    out("")
    out("ROUTE PROBES:")
    probe_failures = run_probes(live, base_url, client=probe_client,
                                token_reader=token_reader, out=out)
    out("")
    if probe_failures:
        if has_writes:
            out(f"RESULT: FAIL ({probe_failures} expected probe failure(s)). The files "
                f"were all written; this run did NOT roll them back.")
            out(f"BACKUP: {backup.root} (journal: {backup.journal.name})")
            if written:
                out(f"        wrote {len(written)} file(s); full write, partial deploy "
                    f"verification")
            out("        Restart Jarvis, re-check, or run --rollback <the backup folder> "
                "to put the files back.")
        else:
            out(f"RESULT: FAIL ({probe_failures} expected probe failure(s)). Nothing "
                "was written in this run, so there is nothing to restore.")
        return 1
    out("RESULT: PASS - backend reconciled; restart Jarvis and read the start-up banner.")
    if written:
        out(f"        wrote {len(written)} file(s); backup in {backup.root}")
    else:
        out("        no file changed (already current)")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deploy the repository's backend onto the live Jarvis folder safely "
                    "(dry run by default).")
    parser.add_argument("--backend-path", required=True,
                        help="the folder holding the live jarvis_hud.py")
    parser.add_argument("--repo", default="",
                        help="the repository checkout (default: this tool's parent folder)")
    parser.add_argument("--ref", default="origin/main",
                        help="git ref whose backend/ blobs are the source (default: origin/main)")
    parser.add_argument("--apply", action="store_true", help="write; without it, dry run")
    parser.add_argument("--dry-run", action="store_true", help="explicit dry run (the default)")
    parser.add_argument("--skip-plugins", action="store_true",
                        help="do not add ready plug-ins")
    parser.add_argument("--base-url", default="",
                        help="live server base URL for the probes (default: from HUD_PORT)")
    parser.add_argument("--rollback", default="",
                        help="restore a previous backup folder's journal and exit "
                             "(does not deploy)")
    ns = parser.parse_args(argv)
    if ns.rollback:
        return rollback_backup(Path(ns.backend_path).expanduser(), Path(ns.rollback))
    if ns.apply and ns.dry_run:
        print("Choose one: --apply or --dry-run (dry run is the default).")
        return 2
    repo = Path(ns.repo) if ns.repo else Path(__file__).resolve().parent.parent
    try:
        return run_deploy(repo, Path(ns.backend_path).expanduser(), apply=bool(ns.apply),
                          ref=ns.ref, skip_plugins=bool(ns.skip_plugins),
                          base_url=ns.base_url)
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2
    except KeyboardInterrupt:
        print("Stopped.")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
