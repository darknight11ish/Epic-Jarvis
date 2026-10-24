#!/usr/bin/env python3
"""Review #2 (chaos / failure probes), HERMETIC ONLY: inject the fault, then
check the shipped code's own answer to it.

    python -B tools/check_fault_probes.py [-v] [--json] [--list] [--root DIR]
    python -B tools/check_fault_probes.py --probe fp-busy

WHY THIS EXISTS, AND WHY IT IS NOT A MOCK. The 10-Review Playbook's Review #2
asks for eight fault-injection scenarios; the owner's ruling of 2026-10-23
(PB-Q2, `deepseek_unified_master_rulings_and_wave3_review_2026_10_23.md` §4.1)
splits them into a hermetic copy only and live hardware, and says in as many
words that destructive faults must never touch the owner's real
`~/.openjarvis/`. This tool is the hermetic half: every probe runs against a
throwaway folder shaped like the owner's PC (its own `OPENJARVIS_HOME`,
`JARVIS_HOME`, log folder and content-risk state), with the fault injected
deterministically, and no network, no real backend, no model and no sleep that
decides an outcome.

WHAT MAKES A PROBE HONEST, AND WHAT DOES NOT. A probe is not allowed to hand
the product a fake answer and then test the fake. It injects the fault at the
boundary the operating system would fail at, and then reads the PRODUCT's own
answer:

  * a real held SQLite write lock, and the product's own connection is asked
    to commit through it;
  * a real `disk_usage` reading of 4,096 free bytes, and the product's own
    pre-flight is asked whether the copy may start;
  * a copy process that dies inside `copytree` (`os._exit`), which is the state
    a SIGKILL leaves - no handler ran, nothing was cleaned up - and the real
    vault is then hashed to see whether "copy first" held;
  * the product's own `PRAGMA busy_timeout`, read back from the connection it
    just handed out, and its own `_load_state()` over a corrupt state file.

The one deliberate simulation is named where it happens: the disk-full probe
replaces `shutil.disk_usage` with a stub, because a truly full disk is not
something a test may arrange on the owner's PC. That is the harness the ruling
itself names ("injected `shutil.disk_usage` stub").

THE MUTATION-SANITY PROOF IS NOT IN THIS FILE. A checker that cannot fail is
worthless, and the way to know it can fail is to break the code it guards and
watch it say so for the RIGHT reason. `backend/test_fault_probes.py` does that:
it copies the shipped tree, applies one named mutation per probe, and asserts
this checker fails with that probe's expected reason code and that the other
probes still pass. Run it with the suite:

    python -B backend/test_fault_probes.py

WHAT IS BLOCKED IS PRINTED AS BLOCKED. Six scenarios from the ruling and the
playbook cannot be run here at all - they need the owner's hardware, a phone,
the installed desktop app or the gate module, which is a base file and not in
the shipped tree this checker imports. They are listed with the reason, they
are printed on every run, and they are never counted as passes. The project's
rule is absolute: BLOCKED and NOT-TESTABLE are never a pass
(`docs/FIELD-TEST-MATRIX-2026-10-11.md`).

Exit codes: 0 every runnable probe passed; 1 a probe failed; 2 the run could
not be made (bad root, a module missing) - never 0 for "nothing ran".
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
#   What cannot be run here, and why. Printed on every run, never a pass.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Blocked:
    id: str
    scenario: str
    why: str


BLOCKED = (
    Blocked(
        "fp-live-sleep-wake",
        "Chaos-1: Windows Modern Standby / sleep mid-turn, wake recovery",
        "live hardware only (ruling PB-Q2: sleep/wake is safe on the owner's PC "
        "during the P2 field test, not in a hermetic run); no probe here"),
    Blocked(
        "fp-live-ollama-restart",
        "Chaos-2: a benign Temporary-chat ollama.exe restart mid-stream",
        "live hardware only (ruling PB-Q2 lists the benign Ollama restart beside "
        "sleep/wake); the hermetic half - a dead pooled socket - is not injected "
        "here because jarvis_local_http's reset path needs the live server"),
    Blocked(
        "fp-gpu-vram",
        "Chaos-3: GPU driver reset / ComfyUI VRAM collision on the 12 GB card",
        "needs the real cards and a running model; nothing on this harness can "
        "raise or observe a VRAM unload"),
    Blocked(
        "fp-live-roaming-handoff",
        "Chaos-4a: Tailscale/Meshnet roaming drop mid-approval (phone Wi-Fi to 5G)",
        "needs the owner's phone and the private mesh; ruling PB-Q2 puts the "
        "handoff on live hardware only"),
    Blocked(
        "fp-dual-tap-race",
        "Chaos-4b: the 50 ms dual PC+Phone card tap race",
        "the idempotency lives in jarvis_gate.py, which is a base/patch file and "
        "not in the shipped tree this checker imports; proving it needs the gate "
        "suite's card store, so it is not claimed here"),
    Blocked(
        "fp-webview2-reload",
        "WebView2 reload mid-Edit HUD",
        "the HUD is HTML/JS; this is a Python checker and the desktop node "
        "harness (jarvis-desktop/tests/*.mjs) is the right instrument"),
    Blocked(
        "fp-clock-jump",
        "Chaos-8: DST / +/-1 h clock jump with timers armed",
        "hermetic-capable (jarvis_schedule takes an injectable clock) but a probe "
        "would report a PRODUCT FINDING, not a pass: add_timer stores an "
        "absolute wall-clock `due` (jarvis_schedule.py `self.now() + seconds`), "
        "so an injected +1 h jump makes a 10-minute timer look due. Recorded as "
        "a finding for a product lane; never as a pass here"),
)


# --------------------------------------------------------------------------
#   A failure with a reason code, so a caller can prove WHY it failed
# --------------------------------------------------------------------------

class Failure(Exception):
    """A probe's expected failure. `code` is the machine-readable reason the
    mutation-sanity suite asserts on; `detail` is the evidence shown to a
    reader."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def fail(code: str, detail: str = ""):
    raise Failure(code, detail)


# --------------------------------------------------------------------------
#   The sandbox: the owner's-PC shape, thrown away afterwards
# --------------------------------------------------------------------------

def _fresh_dir(base: Path, tag: str) -> Path:
    """A new folder under `base`, made with `os.makedirs`.

    NOT `tempfile.mkdtemp`: in the Windows agent sandbox this tool was written
    in, a folder `mkdtemp` created refused every write beneath it (`WinError
    5`), while the same folder made with `os.makedirs` accepted subfolders and
    files. The uniqueness mkdtemp provides is replaced by a random suffix.
    """
    import uuid
    for _ in range(20):
        candidate = base / f"{tag}-{uuid.uuid4().hex[:10]}"
        try:
            os.makedirs(candidate)
            return candidate
        except FileExistsError:
            continue
    raise OSError(f"no fresh folder name under {base}")


def scratch_base(root: Path, workdir: str = "") -> Path:
    """A SHORT folder this process may make subfolders in, and its reason.

    The system temp folder is the first choice and the one CI uses. It is not
    always usable: some sandboxes (the Windows agent sandbox this was written
    in, on 2026-10-23) let a process create a folder there but refuse every
    write beneath it, and a vault copy needs folders. The fallbacks are
    `.dsh-scratch/fault-probes-tmp` in this tool's own repository first, then
    in the tree being tested - in that order because a mutation suite runs
    this tool against a COPY of the tree, and a copy is deep: nesting the
    sandbox inside it pushed the vault's file paths past Windows' 260-character
    limit, and `copytree` then failed with an `shutil.Error` that had nothing
    to do with the fault. A caller can name a folder with `--workdir`.
    """
    if workdir:
        base = Path(workdir)
        base.mkdir(parents=True, exist_ok=True)
        _fresh_dir(base, "probe-check")
        return base
    import tempfile as _tempfile
    base = Path(_tempfile.mkdtemp(prefix="fault-probes-"))
    try:
        _fresh_dir(base, "probe-check")
        return base
    except OSError:
        shutil.rmtree(base, ignore_errors=True)
    for fallback in (REPO / ".dsh-scratch" / "fault-probes-tmp",
                     root / ".dsh-scratch" / "fault-probes-tmp"):
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback
        except OSError:
            continue
    raise OSError("no scratch folder could be made under temp, this repo or the root")


class Sandbox:
    """A temporary folder shaped like the owner's PC, and modules imported from
    `root` (the repository, or a copy of it the mutation suite made).

    `OPENJARVIS_HOME`, `JARVIS_HOME` and `JARVIS_LOG_DIR` are pointed at the
    throwaway folder before any product module is imported, because the modules
    read them at import time. Every product module is dropped from
    `sys.modules` before an import so a probe never inherits a module that read
    the previous probe's environment.
    """

    def __init__(self, root: Path, tag: str, base: Path | None = None):
        self.root = Path(root)
        self.tag = tag
        self.base = base
        self.dir: Path | None = None
        self._saved_env: dict = {}
        self._saved_path: list = []

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> "Sandbox":
        assert self.base is not None
        self.dir = _fresh_dir(Path(self.base), f"fault-{self.tag}")
        home = self.dir / "home"
        logs = self.dir / "logs"
        home.mkdir()
        logs.mkdir()
        for key, value in (
            ("OPENJARVIS_HOME", home),
            ("JARVIS_HOME", home),
            ("JARVIS_LOG_DIR", logs),
            ("JARVIS_BACKEND", ""),
        ):
            self._saved_env[key] = os.environ.get(key)
            if value == "":
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)
        self._saved_path = list(sys.path)
        for folder in (self.root / "backend" / "rebuilt", self.root / "backend"):
            if folder.is_dir():
                sys.path.insert(0, str(folder))
        return self

    def __exit__(self, *exc):
        sys.path[:] = self._saved_path
        for key, old in self._saved_env.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        _drop_product_modules()
        if self.dir is not None:
            shutil.rmtree(self.dir, ignore_errors=True)
        return False

    # -- helpers -----------------------------------------------------------
    def path(self, *parts: str) -> Path:
        assert self.dir is not None
        p = self.dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def env(self, key: str, value: str) -> None:
        os.environ[key] = str(value)

    def mod(self, name: str):
        """Import one product module from this sandbox's tree, fresh."""
        _drop_product_modules()
        import importlib
        importlib.invalidate_caches()
        try:
            return importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - reported, never a pass
            fail("module_missing",
                 f"{name} could not be imported from {self.root / 'backend'} "
                 f"({type(exc).__name__}: {exc})")


def _drop_product_modules() -> None:
    for name in [n for n in sys.modules if n.startswith("jarvis_")]:
        sys.modules.pop(name, None)


def _make_vault(folder: Path, notes: dict | None = None) -> Path:
    """A small Obsidian-shaped vault: one folder, a few notes."""
    vault = folder
    (vault / "Daily").mkdir(parents=True)
    for name, body in (notes or {
        "Daily/2026-10-20.md": "# Monday\n- ship the review harness\n",
        "Daily/2026-10-21.md": "# Tuesday\n- read the fault probes\n",
        "index.md": "# Vault\nhome note\n",
    }).items():
        target = vault / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, "utf-8")
    return vault


def _sha_tree(root: Path) -> str:
    """The product's own tree digest, so the probe measures with the same
    instrument the copy-first rule uses."""
    return _sha_tree._vo._tree_digest(root)  # type: ignore[attr-defined]


# --------------------------------------------------------------------------
#   The probes. Each one raises Failure(code, detail) or returns evidence.
# --------------------------------------------------------------------------

def probe_busy(sb: Sandbox) -> dict:
    """A real held write lock, and the product's connection asked to commit
    through it.

    Pass: the connection hands out `busy_timeout = 5000` (F10's documented
    value), the waiting write does NOT fail at once, and it lands once the
    lock is released - both rows present.
    """
    sqlite = sb.mod("jarvis_sqlite")
    db = sb.path("busy", "app.db")
    db.parent.mkdir(parents=True, exist_ok=True)

    setup = sqlite.connect(db)
    setup.execute("CREATE TABLE t (x INTEGER)")
    setup.commit()
    setup.close()

    holder = sqlite3.connect(str(db), isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")
    holder.execute("INSERT INTO t VALUES (1)")

    outcome = {"done": False, "err": ""}
    started = threading.Event()

    def writer():
        started.set()
        try:
            conn = sqlite.connect(db)  # the product's own connection
            conn.execute("INSERT INTO t VALUES (2)")
            conn.commit()
            conn.close()
        except Exception as exc:  # noqa: BLE001 - the failure is the evidence
            outcome["err"] = f"{type(exc).__name__}: {exc}"
        finally:
            outcome["done"] = True

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    started.wait(5.0)
    # Bounded hold, not a race: the writer is provably blocked on the lock, so
    # what is asserted at +150 ms is "it is still waiting", not a timing.
    time.sleep(0.15)
    still_waiting = not outcome["done"]
    holder.execute("COMMIT")
    holder.close()
    thread.join(15.0)

    if not still_waiting:
        fail("raised_immediately",
             "the write did not wait for the held lock: "
             f"{outcome['err'] or 'it finished while the lock was held'}")
    if outcome["err"]:
        fail("database_is_locked",
             f"the write failed instead of waiting: {outcome['err']}")
    if not outcome["done"]:
        fail("write_hung", "the write never returned after the lock was released")

    check = sqlite.connect(db)
    rows = check.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    busy = check.execute("PRAGMA busy_timeout").fetchone()[0]
    check.close()
    if rows != 2:
        fail("rows_lost", f"expected 2 rows after the wait, found {rows}")
    if int(busy) != 5000:
        fail("busy_timeout_not_5000",
             f"the product's connection reports busy_timeout={busy}, and F10's "
             "documented value is 5000")
    return {"rows": rows, "busy_timeout": int(busy)}


def probe_winerror32(sb: Sandbox) -> dict:
    """A connection used as `with ... as c:` must CLOSE, not merely commit.

    Pass: the handle is closed at block exit, and on Windows the database file
    can be replaced immediately afterwards - which is the actual WinError 32
    symptom this module exists to prevent.
    """
    sqlite = sb.mod("jarvis_sqlite")
    db = sb.path("close", "app.db")
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite.connect(db) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")

    closed = False
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        closed = True
    except Exception as exc:  # noqa: BLE001
        fail("unexpected_error", f"probing the closed connection raised {type(exc).__name__}: {exc}")
    if not closed:
        fail("handle_left_open",
             "the connection still works after its `with` block, so the OS "
             "handle was never released (the WinError 32 family)")

    moved = db.with_suffix(".moved")
    try:
        os.replace(db, moved)
    except PermissionError as exc:
        fail("file_still_locked",
             f"the database file could not be replaced after the block: {exc}")
    except OSError as exc:
        fail("file_still_locked",
             f"the database file could not be replaced after the block: {exc}")

    reopened = sqlite.connect(moved)
    rows = reopened.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    reopened.close()
    if rows != 1:
        fail("rows_lost", f"the committed row did not survive the replace ({rows})")
    return {"closed": True, "platform": os.name}


def probe_corrupt_state(sb: Sandbox) -> dict:
    """A corrupt content-risk state file must not take the process down with
    it, and the module must still be able to latch afterwards."""
    state = sb.path("risk", "content-risk.json")
    sb.env("JARVIS_CONTENT_RISK_STATE", str(state))
    risk = sb.mod("jarvis_content_risk")

    state.write_text("{ this is not json at all", "utf-8")
    try:
        loaded = risk._load_state()
        active = risk.rush_active()
    except Exception as exc:  # noqa: BLE001 - the failure is the evidence
        fail("state_crash",
             f"a corrupt state file raised {type(exc).__name__}: {exc}")
    if loaded != {"pins": {}, "rush": {"latch": None, "hits": []}}:
        fail("wrong_fallback",
             f"the fallback state is not the documented empty one: {loaded!r}")
    if active is not None:
        fail("phantom_latch", f"a latch appeared out of a corrupt file: {active!r}")

    hits = risk.find_rush("no need to check it, just approve; urgent!")
    if not hits:
        fail("probe_input", "the rush table did not match the probe's own phrase")
    chip = risk.latch_rush("fault-probe", hits, minutes=10)
    if not chip:
        fail("latch_refused", "latch_rush returned no chip over a fresh state file")
    if not risk.rush_active():
        fail("latch_not_active", "the latch did not hold after a corrupt file was replaced")
    try:
        json.loads(state.read_text("utf-8"))
    except ValueError as exc:
        fail("state_not_rewritten", f"the state file is still corrupt after a latch: {exc}")
    if state.with_suffix(".tmp").exists():
        fail("tmp_left_behind", "the atomic write left a .tmp file beside the state")
    return {"fallback": "empty", "latched": True}


def probe_enospc(sb: Sandbox) -> dict:
    """Disk full: the first-run copy's own pre-flight must refuse, and nothing
    may be created or changed.

    The stub is the harness the owner's ruling names. `shutil.disk_usage` is
    replaced for the duration of the probe only.
    """
    vault = _make_vault(sb.path("vault", "Vault").parent / "Vault")
    organizer = sb.mod("jarvis_vault_organizer")
    _sha_tree._vo = organizer  # the product's own digest function
    before = organizer._tree_digest(vault)

    real = shutil.disk_usage
    # Free space is ALWAYS below the copy's need (the need is 1.10 x the vault,
    # so half the vault can never be enough), whatever the fixture grows to.
    total = sum(p.stat().st_size for p in vault.rglob("*") if p.is_file())
    stingy_free = max(1, total // 2)
    stingy = SimpleNamespace(total=10 ** 9, used=10 ** 9 - stingy_free, free=stingy_free)
    organizer.shutil.disk_usage = lambda path: stingy
    try:
        pre = organizer._copy_preflight(vault)
    finally:
        organizer.shutil.disk_usage = real

    copies = [p.name for p in vault.parent.iterdir()
              if p.name.startswith(vault.name + organizer.COPY_SUFFIX)]
    if copies:
        fail("copy_started", f"a copy folder was created anyway: {copies}")
    if pre.get("ok") is not False:
        fail("enospc_allowed",
             f"the pre-flight allowed a copy with only {stingy_free} free bytes: {pre!r}")
    why = str(pre.get("why") or "")
    if "free" not in why:
        fail("refusal_unclear", f"the refusal does not name the free space: {why!r}")
    if organizer._tree_digest(vault) != before:
        fail("vault_changed", "the refusal still changed the real vault")

    after = organizer._copy_preflight(vault)  # with the real disk_usage back
    if after.get("ok") is not True:
        fail("clean_refused",
             f"with room free the pre-flight still refuses: {after!r}")
    return {"refusal": why[:120], "free_bytes": stingy_free,
            "need_bytes": after.get("need_bytes")}


CHILD_TORN_COPY = r"""
import os, sys
root, vault = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(root, "backend", "rebuilt"))
sys.path.insert(0, os.path.join(root, "backend"))
import pathlib
import shutil as _sh
import jarvis_vault_organizer as VO


def torn(src, dst, **kwargs):
    # A copy that dies partway: one file lands, then the process is gone - the
    # state SIGKILL leaves (no exception handler runs, no cleanup runs).
    os.makedirs(dst)
    names = sorted(n for n in os.listdir(src)
                   if os.path.isfile(os.path.join(src, n)))
    if names:
        with open(os.path.join(src, names[0]), "rb") as fh:
            data = fh.read()
        with open(os.path.join(dst, names[0]), "wb") as fh:
            fh.write(data)
    os._exit(137)


VO.shutil.copytree = torn
VO._make_copy(pathlib.Path(vault))
os._exit(0)
"""


def probe_torn_copy(sb: Sandbox) -> dict:
    """Power loss / SIGKILL during the vault copy: the real vault must be
    byte-identical, because the organizer copies first and organizes the copy.

    The child process calls the product's own `_make_copy` and dies inside
    `copytree` (`os._exit(137)`) - nothing catches it, nothing cleans up,
    which is exactly what the operating system leaves after a kill. Then the
    real vault is hashed, and a second, ordinary copy is made from a fresh
    process to prove the vault is still usable.
    """
    organizer = sb.mod("jarvis_vault_organizer")
    _sha_tree._vo = organizer
    vault = _make_vault(sb.path("vault", "Vault").parent / "Vault")
    before = organizer._tree_digest(vault)

    env = dict(os.environ)
    env.pop("JARVIS_BACKEND", None)
    done = subprocess.run(
        [sys.executable, "-B", "-c", CHILD_TORN_COPY, str(sb.root), str(vault)],
        cwd=str(sb.dir), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180)
    if done.returncode != 137:
        fail("kill_not_reached",
             "the copy process was expected to die inside copytree (137), got "
             f"{done.returncode}: {(done.stderr or done.stdout or '').strip()[:300]}")

    after = organizer._tree_digest(vault)
    if after != before:
        fail("vault_changed",
             "the real vault changed while a copy died partway: the copy-first "
             "promise did not hold")

    partial = [p for p in vault.parent.iterdir()
               if p.is_dir() and p.name.startswith(vault.name + organizer.COPY_SUFFIX)]
    if not partial:
        fail("kill_not_mid_copy",
             "no partial copy was found, so the kill did not land inside the copy")

    # Recovery: a fresh, ordinary copy from the untouched vault still works.
    # `_make_copy` catches its own exception and returns words, so the reason
    # copytree gave is collected here - a diagnosis, not a guess.
    said = []
    real_copytree = organizer.shutil.copytree

    def _spy(*positional, **kwargs):
        try:
            return real_copytree(*positional, **kwargs)
        except Exception as exc:  # noqa: BLE001 - reported below
            said.append(f"{type(exc).__name__}: {exc}")
            raise

    organizer.shutil.copytree = _spy
    try:
        made = organizer._make_copy(vault)
    finally:
        organizer.shutil.copytree = real_copytree
    if not made.get("ok"):
        fail("no_recovery",
             f"a second copy after the kill failed: {made!r} "
             f"copytree said: {' | '.join(said) or '(it did not raise)'}")
    if organizer._tree_digest(Path(made["copy"])) != before:
        fail("copy_not_equal",
             "the recovery copy is not byte-identical to the real vault")
    return {"killed_exit": done.returncode,
            "partial": partial[0].name, "recovered": True}


PROBES = (
    ("fp-busy", "a held SQLite write lock: the write waits, then lands", probe_busy),
    ("fp-winerror32", "a `with` connection closes its file handle (WinError 32 family)", probe_winerror32),
    ("fp-corrupt-state", "a corrupt content-risk state file: no crash, the latch still works", probe_corrupt_state),
    ("fp-enospc", "disk full: the copy pre-flight refuses and writes nothing", probe_enospc),
    ("fp-torn-copy", "a copy killed partway: the real vault is untouched and still copyable", probe_torn_copy),
)


# --------------------------------------------------------------------------
#   Running them
# --------------------------------------------------------------------------

def run_probe(probe_id: str, fn, root: Path, base: Path) -> dict:
    started = time.perf_counter()
    try:
        with Sandbox(root, probe_id, base) as sb:
            evidence = fn(sb)
        return {"id": probe_id, "status": "pass", "evidence": evidence or {},
                "seconds": round(time.perf_counter() - started, 3)}
    except Failure as exc:
        return {"id": probe_id, "status": "fail", "reason": exc.code,
                "detail": exc.detail, "seconds": round(time.perf_counter() - started, 3)}
    except Exception as exc:  # noqa: BLE001 - a crash is a failure, never a pass
        return {"id": probe_id, "status": "fail", "reason": "crashed",
                "detail": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc()[-1500:],
                "seconds": round(time.perf_counter() - started, 3)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Review #2 hermetic fault probes: inject the fault, read "
                    "the shipped code's answer.")
    parser.add_argument("--root", default=str(REPO),
                        help="tree to import the product modules from (default: this repo)")
    parser.add_argument("--workdir", default="",
                        help="scratch folder for the throwaway sandboxes (default: system temp, "
                             "then <root>/.dsh-scratch/fault-probes-tmp)")
    parser.add_argument("--probe", action="append", default=[],
                        help="run only this probe id (repeatable)")
    parser.add_argument("--json", action="store_true", help="machine-readable result")
    parser.add_argument("--list", action="store_true",
                        help="print every probe and blocked row, run nothing")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print each probe's evidence")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / "backend").is_dir():
        print(f"NO RUN: {root} has no backend/ folder to import", file=sys.stderr)
        return 2
    try:
        base = scratch_base(root, args.workdir)
    except OSError as exc:
        print(f"NO RUN: no scratch folder to run the probes in ({exc})", file=sys.stderr)
        return 2

    chosen = list(PROBES)
    if args.probe:
        known = {p[0] for p in PROBES}
        unknown = [p for p in args.probe if p not in known]
        if unknown:
            print(f"NO RUN: unknown probe(s): {', '.join(unknown)}; known: "
                  f"{', '.join(sorted(known))}", file=sys.stderr)
            return 2
        chosen = [p for p in PROBES if p[0] in args.probe]

    if args.list:
        for pid, name, _fn in PROBES:
            print(f"PROBE   {pid:<18} {name}")
        for row in BLOCKED:
            print(f"BLOCKED {row.id:<18} {row.scenario}\n        {row.why}\n        "
              f"NOT a pass.")
        return 0

    results = [run_probe(pid, fn, root, base) for pid, _name, fn in chosen]
    passed = [r for r in results if r["status"] == "pass"]
    failed = [r for r in results if r["status"] != "pass"]

    if args.json:
        print(json.dumps({"root": str(root), "probes": results,
                          "blocked": [row.__dict__ for row in BLOCKED],
                          "passed": len(passed), "failed": len(failed)},
                         indent=1, sort_keys=True))
        return 0 if not failed else 1

    print(f"Review #2 fault probes (hermetic only) - modules from {root / 'backend'}")
    names = {pid: name for pid, name, _fn in PROBES}
    for result in results:
        if result["status"] == "pass":
            extra = ""
            if args.verbose and result.get("evidence"):
                extra = f"  evidence={json.dumps(result['evidence'], sort_keys=True)}"
            print(f"PASS    {result['id']:<18} {names[result['id']]}{extra}")
        else:
            print(f"FAIL    {result['id']:<18} {names[result['id']]}")
            print(f"        reason={result['reason']}  {result.get('detail', '')}")
    for row in BLOCKED:
        print(f"BLOCKED {row.id:<18} {row.scenario}")
        print(f"        {row.why}")
        print("        NOT a pass.")
    print(f"{len(passed)} passed, {len(failed)} failed, {len(BLOCKED)} blocked "
          f"(BLOCKED rows are not passes)")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
