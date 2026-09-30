"""test_telemetry_off.py - libraries are told not to report usage (supply-chain
audit, 2026-09-30).

    python3 backend/test_telemetry_off.py

What it proves:
  - importing jarvis_child_env (which the modules that start models import)
    sets HF_HUB_DISABLE_TELEMETRY=1, DO_NOT_TRACK=1 and ANONYMIZED_TELEMETRY=False
    in the process - checked in a FRESH Python, so this test's own environment
    cannot fake it;
  - a value the owner has set on purpose is left alone (setdefault);
  - every program Jarvis starts through `inherited` gets the three, and still
    gets none of the owner's secrets;
  - the F5 worker's environment has them (jarvis_voices.worker_env);
  - the start line in docs/INSTALL.md sets them before any library loads.
Said plainly: these three names only. sherpa-onnx's own ONNX Runtime has no
switch Jarvis can reach (docs/ARCHITECTURE.md). No network, no model.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_child_env.py", "jarvis_voices.py")
import jarvis_child_env as CE  # noqa: E402

PASSED, FAILED = [], []
NAMES = ("HF_HUB_DISABLE_TELEMETRY", "DO_NOT_TRACK", "ANONYMIZED_TELEMETRY")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def fresh_python(extra_env: dict) -> dict:
    """The three names as a brand-new Python sees them right after importing
    jarvis_child_env, started with `extra_env` and none of the three."""
    env = {k: v for k, v in os.environ.items() if k not in NAMES}
    env.update(extra_env)
    env["PYTHONPATH"] = str(HERE)
    code = ("import os, json; import jarvis_child_env; "
            "print(json.dumps({k: os.environ.get(k) for k in "
            + repr(list(NAMES)) + "}))")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                         text=True, timeout=60, cwd=str(HERE))
    import json
    return json.loads(out.stdout.strip().splitlines()[-1])


def main() -> int:
    got = fresh_python({})
    check("importing jarvis_child_env switches all three off in the process",
          got == {"HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1",
                  "ANONYMIZED_TELEMETRY": "False"}, got)
    got = fresh_python({"DO_NOT_TRACK": "0"})
    check("a value the owner set on purpose is not overwritten", got["DO_NOT_TRACK"] == "0", got)

    env = CE.inherited({"PATH": "/bin", "HUD_TOKEN": "secret", "OPENAI_API_KEY": "k"})
    check("every program Jarvis starts gets the three switches",
          all(env.get(k) == v for k, v in CE.TELEMETRY_OFF.items()), env)
    check("... and still none of the owner's secrets",
          "HUD_TOKEN" not in env and "OPENAI_API_KEY" not in env and env.get("PATH") == "/bin", env)
    check("the switches are not copied from the owner's environment (a hostile "
          "'DO_NOT_TRACK=0' there cannot switch the children's back on)",
          CE.inherited({"DO_NOT_TRACK": "0"}).get("DO_NOT_TRACK") == "1")

    import jarvis_voices as V
    w = V.worker_env("GPU-12345678-aaaa-bbbb-cccc-1234567890ab", base={"PATH": "/bin"})
    check("the F5 worker's environment has all three",
          w.get("HF_HUB_DISABLE_TELEMETRY") == "1" and w.get("DO_NOT_TRACK") == "1"
          and w.get("ANONYMIZED_TELEMETRY") == "False", w)

    text = (REPO / "docs" / "INSTALL.md").read_text(encoding="utf-8")
    lines = [l for l in text.splitlines() if "py -3 jarvis_hud.py" in l and l.startswith("cd ")]
    check("both start lines in docs/INSTALL.md set the three switches first",
          len(lines) == 2 and all(all(f'$env:{n} =' in l for n in NAMES) for l in lines), lines)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
