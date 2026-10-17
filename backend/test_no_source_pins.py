"""tools/check_no_source_pins.py is the gate, and this proves it is green and honest.

    python3 backend/test_no_source_pins.py

WHY THIS EXISTS. `tools/check_no_source_pins.py` is a CEILING RATCHET against a
test pinning the source TEXT of a production module instead of exercising the
seam at runtime. Seven checks in this project passed that way, so the rule has to
be mechanical rather than remembered. This suite is the proof the gate exists,
runs, and cannot quietly lose its own measurement:

  * the tool exits 0 on this tree (the debt is inside its recorded ceilings);
  * it PRINTS the numbers - how many files still pin source text, so a decrease
    is visible and "nothing is wrong" cannot be confused with "nothing was
    looked at";
  * `--measure` reports the SAME total the ceiling table records, so the table
    cannot drift away from the measurement in either direction. A ratchet whose
    recorded number no longer equals the measured one has stopped ratcheting.

The bite proof for the check itself (a planted pin fails it, a raised ceiling
fails it, and an `ast.parse()`-based check is NOT flagged) is in the pull
request that added it - the same rule this checker enforces: prove a historical
claim in the record of the change, not by re-running history in a standing test.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOL = REPO / "tools" / "check_no_source_pins.py"

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def run(*args):
    return subprocess.run([sys.executable, "-B", str(TOOL), *args],
                          cwd=str(REPO), capture_output=True, text=True, encoding="utf-8")


def main() -> int:
    gate = run()
    out = (gate.stdout or "") + (gate.stderr or "")
    check("the source-pin gate is green on this tree", gate.returncode == 0, out[-800:])
    check("... and it says a number, so 'nothing is wrong' cannot be 'nothing was looked at'",
          "file(s) still pin source text" in out, out[-800:])
    check("... and it says what to do instead of pinning text",
          "ast" in out and "ceiling" in out, out[-800:])

    measured = run("--measure")
    mout = (measured.stdout or "") + (measured.stderr or "")
    check("--measure runs", measured.returncode == 0, mout[-400:])
    # The recorded total must equal the measured total: a ratchet that no longer
    # matches its measurement has stopped ratcheting in one direction or the other.
    import importlib.util
    spec = importlib.util.spec_from_file_location("no_source_pins", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    found = mod.measure()
    recorded = sum(mod.SOURCE_PIN_CEILING.values())
    now = sum(len(v) for v in found.values())
    check("the recorded ceiling total equals what is measured today", recorded == now,
          f"recorded {recorded}, measured {now}")
    for f, hits in found.items():
        if mod.SOURCE_PIN_CEILING.get(f, 0) != len(hits):
            check(f"{f}: recorded ceiling matches the measurement",
                  False, f"recorded {mod.SOURCE_PIN_CEILING.get(f, 0)}, measured {len(hits)}")

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
