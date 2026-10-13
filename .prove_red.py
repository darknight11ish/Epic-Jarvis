"""Does this change actually cause the behaviour backend/test_gate_no_expiry.py
claims? Run the same assertions against the gate WITHOUT it and WITH it.

    python .prove_red.py

WHY A SCRIPT OF ITS OWN. `test_gate_no_expiry.py` BUILDS the gate by applying
`no-expiry-cards.patch` to the published base, so by construction it cannot run
"without the change" - the patch is what it applies. That makes it a
patch-verifier, which is what this repository asks of a patch (the suite proves
the patch's real output, on the file the patch is published against), and it
leaves one question open: would these assertions have caught the bug if the
change were absent? This answers it the only way that means anything - the
same assertions, twice, on a gate built with and without the patch.

WHAT THE TWO RUNS ARE, and what this prints:

    WITHOUT the patch                    WITH the patch
    ----------------------------------   --------------------------------
    timeout_for('pair_device') -> 180    -> None (the card waits)
    timeout_for('send_email')  -> 180    -> 180 (routine, unchanged)
    an hour on, a deliberate card:       still pending, then approved
      gone / refused 'timed_out'
    the start-up sweep past the grace    left alone: 'pending'
      period: 'expired'
    a deliberate card's pending row:     no expires_in at all
      expires_in present
    owner_check._time_left({'expires_in': None}) -> 180 -> None
    ..._time_left({})  (no expires_in field at all) -> 180 -> 180
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "backend"))
import _gitapply  # noqa: E402
from _where import REPO  # noqa: E402

PATCH = HERE / "backend" / "no-expiry-cards.patch"
FILES = ("jarvis_gate.py", "jarvis_owner_check.py", "jarvis_devices.py")
TIMEOUT = 180


def build(with_patch: bool) -> Path:
    """The published base, from HEAD, with the patch or without it."""
    d = Path(tempfile.mkdtemp(prefix="prove-red-"))
    git = shutil.which("git")
    for name in FILES:
        want = subprocess.run([git, "-C", str(REPO), "show",
                               f"HEAD:jarvis-backend/{name}"],
                              capture_output=True).stdout
        (d / name).write_bytes(want.replace(b"\r\n", b"\n"))
    if with_patch:
        env = _gitapply.env_for(git, d)
        r = subprocess.run([git, "-c", "core.autocrlf=false", "apply", str(PATCH)],
                           cwd=str(d), capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
    return d


def load(folder: Path, name: str):
    """Import `name` out of `folder`, freshly, with a settings stub."""
    cfg = Path(tempfile.mkdtemp(prefix="prove-red-state-"))
    os.environ["JARVIS_APPROVALS_DB"] = str(cfg / "approvals.db")
    os.environ["JARVIS_APPROVAL_TIMEOUT"] = str(TIMEOUT)
    os.environ["JARVIS_NTFY_TOPIC"] = ""
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = cfg
    fw.LOG_DIR = cfg
    fw.load_framework = lambda: {"logging": {}, "autonomy": {
        "unknown_action_tier": "ask",
        "tiers": {"pair_device": "ask", "send_email": "ask"}}}
    fw.audit_log = lambda *a, **k: None
    sys.modules["jarvis_framework"] = fw
    for mod in [n for n in sys.modules if n.startswith(name)]:
        del sys.modules[mod]
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    return __import__(name)


class Clock:
    """A frozen clock: only the script moves it."""

    def __init__(self):
        self.now = time.time()

    def time(self):
        return self.now

    def sleep(self, seconds):
        pass

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += float(seconds)


def line(label, without, with_):
    print(f"  {label:<44} {str(without):<28} {str(with_)}")


def run(with_patch: bool) -> dict:
    out = {}
    G = load(build(with_patch), "jarvis_gate")

    # 1. What the timeout is, per action.
    for action, key in (("pair_device", "pair"), ("send_email", "mail")):
        out[key] = (G.timeout_for(action) if hasattr(G, "timeout_for") else TIMEOUT)

    # 2. An hour of simulated time on a deliberate card.
    G.time = Clock()
    box = {}
    t = threading.Thread(target=lambda: box.setdefault(
        "v", G.check("pair_device", {}, prompt="pair")), daemon=True)
    t.start()
    row = None
    for _ in range(500):
        time.sleep(0.01)
        rows_now = G.pending()
        if rows_now:
            row = rows_now[0]
            break
    if row is None:
        out["expires_in"] = "no card at all"
        out["after"] = "no card at all"
    else:
        out["expires_in"] = "present" if "expires_in" in row else "absent"
        G.time.advance(3600.0)
        time.sleep(0.3)
        if G.pending():
            # Stamped the way a real approval is: an approval nothing stamped
            # is refused (owner-check.patch), which is the protection, not the
            # thing under test here.
            OC0 = load(build(with_patch), "jarvis_owner_check")
            OC0.stamp(row["id"], row["action"])
            G.decide(row["id"], True, by="the proof")
            t.join(timeout=10)
            v = box.get("v")
            answer = getattr(v, "outcome", None)
            out["after"] = f"still pending -> {answer}" if v else "still pending"
        else:
            t.join(timeout=10)
            v = box.get("v")
            out["after"] = f"gone -> {getattr(v, 'outcome', v)}"
    G.time = time

    # 3. The start-up sweep, past its grace period.
    G2 = load(build(with_patch), "jarvis_gate")
    G2.time = Clock()
    G2._init()
    import sqlite3
    c = sqlite3.connect(str(G2.DB_PATH), timeout=5.0, isolation_level=None)
    c.execute("INSERT INTO approvals (id,action,tier,detail,prompt,state,created,raised)"
              " VALUES ('sweep','pair_device','ask','{}','','pending',?,NULL)",
              (G2.time.now - TIMEOUT - 600,))
    c.close()
    G2._inited = False
    G2._init()
    state = [r["state"] for r in G2.history(5) if r["id"] == "sweep"]
    out["sweep"] = state[0] if state else "gone"
    G2.time = time

    # 4. The Windows Hello half. `{"expires_in": None}` is the row the gate
    # actually sends for a card with no deadline; `{}` is a row from a backend
    # without approval-expiry.patch, which keeps its window on purpose.
    OC = load(build(with_patch), "jarvis_owner_check")
    out["time_left"] = (OC._time_left({"expires_in": None})
                        if hasattr(OC, "_time_left") else "-")
    out["time_left_missing"] = OC._time_left({}) if hasattr(OC, "_time_left") else "-"
    return out


def main() -> int:
    print(f"  {'':<44} {'WITHOUT the patch':<28} WITH the patch")
    print(f"  {'-' * 44} {'-' * 28} {'-' * 20}")
    no, yes = run(False), run(True)
    for key, label in (("pair", "timeout_for('pair_device')"),
                       ("mail", "timeout_for('send_email')  (routine)"),
                       ("expires_in", "expires_in on a deliberate card"),
                       ("after", "an hour on, a deliberate card"),
                       ("sweep", "the start-up sweep, past the grace period"),
                       ("time_left", "owner_check._time_left({'expires_in': None})"),
                       ("time_left_missing", "..._time_left({})  (no field at all)")):
        line(label, no.get(key, "-"), yes.get(key, "-"))
    ok = (no["pair"] == TIMEOUT and yes["pair"] is None
          and no["mail"] == TIMEOUT == yes["mail"]
          and no["expires_in"] == "present" and yes["expires_in"] == "absent"
          and no["sweep"] == "expired" and yes["sweep"] == "pending"
          and no["time_left"] == TIMEOUT and yes["time_left"] is None
          and no["time_left_missing"] == TIMEOUT == yes["time_left_missing"])
    print(f"\n  every one of those is the change, and the suite's assertions "
          f"distinguish the two runs: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
