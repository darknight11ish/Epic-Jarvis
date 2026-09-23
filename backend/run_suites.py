"""Run every backend suite that can run without the owner's PC, and skip - by
name, with the reason - the ones that cannot. This is what CI runs.

    python3 backend/run_suites.py

WHY A RUNNER AND NOT JUST A LOOP. About twenty suites test a patch against the
file it patches - jarvis_hud.py, jarvis_gate.py, jarvis_extract.py,
jarvis_models.py - and those files live only on the owner's PC, never in this
repository (backend/.gitignore refuses them). Run anywhere else, those suites
fail with an ImportError that looks exactly like a broken patch. A CI job
that is always red teaches everyone to ignore it, so those suites are
SKIPPED here, each one named with the files it is waiting for - and only
while those files are absent. Every other suite must pass.

THE BACKEND IT RUNS AGAINST. Not this folder: a temporary folder holding a
copy of every module apply-patches.ps1 ships (backend/_where.py SHIPPED),
side by side, the way they sit on the owner's PC - rebuilt/ flattened in.
So the suites exercise the shipped LAYOUT, not the repository's folders, and
a module that only works because of where it sits in this repository fails
here. Set JARVIS_BACKEND to run against a real backend instead; then nothing
is staged, and a suite is skipped only if its files are really not there.

The skip list is explicit, not guessed from a failure: a suite that is not in
it and fails is a failure, and a suite in it whose files ARE present runs.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _where  # noqa: E402

# Suite -> the backend files it needs. Found by running each suite in a
# checkout without them and reading which import or file read failed first,
# then reading the suite for its other imports and BACKEND / "..." reads.
# Every entry names at least one file that only the owner's PC has
# (OWNER_FILES), which is what makes it skip here; the rebuilt modules it
# also uses are listed for completeness. test_embedding_guard.py is NOT here:
# it needs only jarvis_memory.py, the staged rebuilt copy satisfies it, and
# it passes against that copy - so it runs.
NEEDS_OWNER = {
    "test_appearance.py": ("jarvis_hud.py",),
    "test_approval_notice.py": ("jarvis_gate.py", "jarvis_events.py"),
    "test_bitemporal.py": ("jarvis_hud.py", "jarvis_memory.py"),
    "test_decide_once.py": ("jarvis_extract.py", "jarvis_hud.py", "jarvis_memory.py"),
    "test_degrade_filter.py": ("jarvis_hud.py",),
    "test_documents_honesty.py": ("jarvis_hud.py",),
    "test_events_pump.py": ("jarvis_hud.py", "jarvis_events.py"),
    "test_extraction_wiring.py": ("jarvis_hud.py", "jarvis_events.py"),
    "test_gate_egress.py": ("jarvis_gate.py", "jarvis_hud.py", "jarvis_events.py"),
    "test_gate_outcome.py": ("jarvis_gate.py",),
    "test_gate_push.py": ("jarvis_gate.py",),
    "test_gpu_offload.py": ("jarvis_hud.py", "jarvis_models.py"),
    "test_import_history.py": ("jarvis_extract.py", "jarvis_memory.py"),
    "test_memory_noise.py": ("jarvis_extract.py", "jarvis_hud.py", "jarvis_memory.py"),
    "test_memory_pane.py": ("jarvis_hud.py",),
    "test_memory_prefix.py": ("jarvis_hud.py",),
    "test_memory_safety.py": ("jarvis_extract.py", "jarvis_memory.py"),
    "test_token_file.py": ("jarvis_hud.py",),
    "test_voice_503.py": ("jarvis_hud.py",),
}

# The files only the owner's PC has. Checked below: every NEEDS_OWNER entry
# must name one, so the list cannot be used to skip a suite that could run.
OWNER_FILES = {"jarvis_hud.py", "jarvis_gate.py", "jarvis_extract.py", "jarvis_models.py",
               "jarvis_skills.py"}


def stage() -> Path:
    d = Path(tempfile.mkdtemp(prefix="jarvis-staged-backend-"))
    for rel in _where.SHIPPED:
        shutil.copy2(HERE / rel, d / rel.rsplit("/", 1)[-1])
    return d


def main() -> int:
    real = os.environ.get("JARVIS_BACKEND")
    backend = Path(real).resolve() if real else stage()
    print(f"backend: {backend}" + ("" if real else "  (staged: every shipped module, flattened)"))
    suites = sorted(HERE.glob("test_*.py"))
    names = {s.name for s in suites}
    stale = sorted(set(NEEDS_OWNER) - names)
    passed, failed, skipped = [], [], []
    if stale:
        print(f"FAIL  run_suites.py lists suites that do not exist: {stale}")
        failed += stale
    no_owner = sorted(k for k, v in NEEDS_OWNER.items() if not set(v) & OWNER_FILES)
    if no_owner:
        print(f"FAIL  run_suites.py skips suites that need nothing from the owner's PC: {no_owner}")
        failed += no_owner
    env = dict(os.environ, JARVIS_BACKEND=str(backend), PYTHONDONTWRITEBYTECODE="1")
    for s in suites:
        need = NEEDS_OWNER.get(s.name, ())
        absent = [f for f in need if not (backend / f).is_file()]
        if absent:
            skipped.append(s.name)
            print(f"skip  {s.name:<34} needs the owner's {', '.join(absent)}")
            continue
        t0 = time.time()
        try:
            r = subprocess.run([sys.executable, str(s)], cwd=HERE, env=env,
                               capture_output=True, text=True, timeout=900)
            code, out = r.returncode, r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            code, out = "timeout", ""
        took = f"{time.time() - t0:5.1f}s"
        if code == 0:
            passed.append(s.name)
            print(f"ok    {s.name:<34} {took}")
        else:
            failed.append(s.name)
            print(f"FAIL  {s.name:<34} {took}  (exit {code})")
            print("\n".join("      " + line for line in out.strip().splitlines()[-40:]))
    if not real:
        shutil.rmtree(backend, ignore_errors=True)
    print(f"\n{len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped "
          f"(they need files that live only on the owner's PC)")
    if failed:
        print("failed: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
