"""jarvis_vault_organizer.py's switch AS A FRESH PROCESS SEES IT.

    python3 backend/test_vault_organizer_switch.py

THE BLIND SPOT THIS CLOSES (measured live 2026-11-09, 16:10-16:22 PT). The
module used to initialise its in-memory marker as `{"id": "", "since": 0.0}` -
a dict that is TRUTHY while holding no card. `request_enabled(True)` tested
`if _PENDING:` before raising a card, so on a fresh backend process the FIRST
"switch the organizer on" answered 202 "one card is already waiting" and
spawned NO card; `switch_status()` reported `waiting: true` with an empty
pending id. `_reconcile_pending()` could not clear it either (it returns False
when the id is empty). The existing suite never saw any of this because
`reset_for_tests()` clears the dict before every check - the harness itself
hid the state the bug lives in.

WHY A SUBPROCESS IS THE HONEST INSTRUMENT. There is no way to un-import a
module in the test process: by the time this file's checks run, the module is
already imported and its marker has whatever history the process gave it. A
child process that imports the module by path and touches nothing else is the
only shape that proves what a backend restart sees. The child is a tiny probe
written into this suite's own temporary folder; it is deleted with the rest of
the folder when the suite ends.

WHAT IT PROVES, in order, against the SHIPPED module (`_where.BACKEND`, which
is this folder unless a real install is named):
  1. a fresh process has no card waiting and has spawned none;
  2. the first ON request raises exactly ONE card and answers the REAL pending
     id - not the empty-marker sentence;
  3. `switch_status()` then reports waiting with that same id;
  4. a second ON while one card waits raises nothing new (202, one card);
  5. running the one card's own decision (the way its thread does) clears the
     marker: enabled, not waiting;
  6. after that, OFF is immediate (200, asks no card) and the next ON raises
     exactly ONE new card.
Nothing here reads or writes the owner's vault or settings: the child's
config folder and HOME are temporary folders under this suite's own `_TMP`,
and the module is loaded by path, never from the live backend folder unless
`JARVIS_BACKEND` deliberately names it (the `_where` rule every suite follows).

EVERY CHECK CAN FAIL. The first one is the regression: with the old
placeholder marker, check 2 sees zero cards and the "one card is already
waiting" sentence, and the suite exits 1.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, require_shipped  # noqa: E402

require_shipped("jarvis_vault_organizer.py")

#: The module under test, resolved the way every suite resolves it.
MODULE = BACKEND / "jarvis_vault_organizer.py"

#: The constants this suite compares the child's answers against. Importing the
#: module HERE is harmless: every stateful check runs in the CHILD, and this
#: process never calls request_enabled/switch_status/reset_for_tests.
import jarvis_vault_organizer as V  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix=".jarvis-vault-organizer-switch-",
                            dir=str(Path.home())))
CONF = TMP / "config"
HOME_DIR = TMP / "home"
CONF.mkdir()
HOME_DIR.mkdir()
CHILD = TMP / "fresh_switch_probe.py"
FAILED, PASSED, SKIPPED = [], [], []
#: The child's private card id is "vc" + 12 hex characters.
_PID = re.compile(r"^vc[0-9a-f]{12}$")

#: The child probe. It imports the module by path, with the module name in
#: `sys.modules` BEFORE `exec_module` (the safe way the live probe loads it),
#: and prints ONE line: `RESULT {json}`. It must never call reset_for_tests() -
#: that call is the blind spot this suite exists to look past.
CHILD_SRC = r'''
import importlib.util
import json
import sys

path = sys.argv[1]
spec = importlib.util.spec_from_file_location("vo_switch_fresh", path)
V = importlib.util.module_from_spec(spec)
sys.modules["vo_switch_fresh"] = V
spec.loader.exec_module(V)


class Verdict:
    tier = "ask"
    allowed = True
    outcome = "approved"


gate_calls = []


def gate(action, detail, prompt):
    gate_calls.append((action, detail, prompt))
    return Verdict()


def tier_of(action):
    return "ask"


cards = []


def spawn(fn):
    cards.append(fn)


def brief(code, body):
    return {"code": code,
            "message": body.get("message"),
            "ok": body.get("ok"),
            "enabled": body.get("enabled"),
            "waiting": body.get("waiting"),
            "pending_id": body.get("pending_id"),
            "pending": body.get("pending")}


def status():
    got = V.switch_status()
    return {"waiting": got.get("waiting"), "pending": got.get("pending"),
            "enabled": got.get("enabled")}


try:
    _p = getattr(V, "_PENDING", None)
    initial_pending = bool(_p)
    initial_pending_repr = repr(_p)
except Exception as exc:                                  # noqa: BLE001
    initial_pending = "unreadable"
    initial_pending_repr = type(exc).__name__

out = {"module": path,
       "initial_pending_truthy": initial_pending,
       "initial_pending": initial_pending_repr,
       "cards_after_import": len(cards),
       "status_before": status()}

code, body = V.request_enabled(True, gate=gate, tier_of=tier_of, spawn=spawn)
out["on1"] = brief(code, body)
out["cards_after_on1"] = len(cards)
out["gate_calls_after_on1"] = len(gate_calls)
out["status_waiting"] = status()

code, body = V.request_enabled(True, gate=gate, tier_of=tier_of, spawn=spawn)
out["on2"] = brief(code, body)
out["cards_after_on2"] = len(cards)
out["gate_calls_after_on2"] = len(gate_calls)

# Resolve the one waiting card exactly as its own daemon thread would. Guarded
# so the OLD buggy module (which spawns no card here) still prints a RESULT:
# the suite then fails check by check, showing the sentence it answered,
# instead of dying on an IndexError and saying nothing about the bug.
if cards:
    cards[0]()
out["resolved_enabled"] = V.enabled()
out["status_after_resolve"] = status()
out["gate_calls_after_resolve"] = len(gate_calls)

code, body = V.request_enabled(False, gate=gate, tier_of=tier_of)
out["off"] = brief(code, body)
out["cards_after_off"] = len(cards)
out["gate_calls_after_off"] = len(gate_calls)

code, body = V.request_enabled(True, gate=gate, tier_of=tier_of, spawn=spawn)
out["on3"] = brief(code, body)
out["cards_after_on3"] = len(cards)
out["gate_calls_after_on3"] = len(gate_calls)

print("RESULT " + json.dumps(out, sort_keys=True))
'''


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def child_env() -> dict:
    """The child's environment: this suite's own folders, and nothing of the
    owner's. The module reads OPENJARVIS_CONFIG_DIR first, so the switch file
    it writes lands in `CONF`; JARVIS_BACKEND is removed so the child cannot
    import a module from the live backend folder by accident."""
    env = dict(os.environ)
    env["OPENJARVIS_CONFIG_DIR"] = str(CONF)
    env["OPENJARVIS_HOME"] = str(HOME_DIR)
    env["JARVIS_HOME"] = str(HOME_DIR)
    env["PYTHONIOENCODING"] = "utf-8"
    env["JARVIS_NO_EMBED"] = "1"
    for name in ("JARVIS_BACKEND", "JARVIS_CONFIG_DIR", "JARVIS_OBSIDIAN_VAULT"):
        env.pop(name, None)
    return env


def run_child() -> dict:
    """Run the fresh-import probe and return its RESULT object, or {}."""
    proc = subprocess.run([sys.executable, "-B", str(CHILD), str(MODULE)],
                          cwd=str(TMP), env=child_env(), capture_output=True,
                          text=True, timeout=180)
    print(f"module: {MODULE}")
    print(f"child exit: {proc.returncode}")
    result = {}
    for line in (proc.stdout or "").splitlines():
        if line.startswith("RESULT "):
            result = json.loads(line[len("RESULT "):])
    if proc.returncode != 0 or not result:
        print("--- child stdout ---")
        print(proc.stdout)
        print("--- child stderr ---")
        print(proc.stderr)
    return result


def one() -> int:
    """Every check, in the child's own order. Returns the number that failed."""
    CHILD.write_text(CHILD_SRC, encoding="utf-8")
    result = run_child()
    r = result

    def got(key, default=None):
        value = r.get(key, default)
        return value if isinstance(value, dict) else (default or {})

    before = got("status_before")
    on1, on2, on3 = got("on1"), got("on2"), got("on3")
    off = got("off")
    waiting = got("status_waiting")
    resolved = got("status_after_resolve")

    check("the fresh child imported the module and nothing else",
          bool(r) and Path(str(r.get("module"))).name == MODULE.name,
          r.get("module"))
    check("a fresh process (no reset_for_tests) has spawned no approval card",
          r.get("cards_after_import") == 0, r.get("cards_after_import"))
    check("... and reports NO card waiting, not an empty pending marker",
          before.get("waiting") is False and before.get("pending") is None,
          before)
    check("the FIRST 'switch it on' raises exactly ONE approval card",
          on1.get("code") == 202 and r.get("cards_after_on1") == 1,
          (on1.get("code"), r.get("cards_after_on1")))
    check("... and asks the gate nothing until that card is decided",
          r.get("gate_calls_after_on1") == 0, r.get("gate_calls_after_on1"))
    check("... and answers the REAL pending id, not the empty-marker sentence",
          isinstance(on1.get("pending_id"), str)
          and bool(_PID.match(on1["pending_id"]))
          and on1.get("waiting") is True and on1.get("pending") is None
          and on1.get("message") == V.SWITCH_ON_WORDS,
          on1)
    check("switch_status() then reports waiting WITH that same pending id",
          waiting.get("waiting") is True
          and isinstance(waiting.get("pending"), dict)
          and waiting["pending"].get("id") == on1.get("pending_id"),
          waiting)
    check("a SECOND ON while one card waits raises nothing new",
          on2.get("code") == 202 and r.get("cards_after_on2") == 1
          and r.get("gate_calls_after_on2") == 0, (on2, r.get("cards_after_on2")))
    check("... it answers 'one card is already waiting', with no new pending id",
          on2.get("message") == "one card is already waiting"
          and on2.get("pending_id") is None
          and isinstance(on2.get("pending"), dict)
          and on2["pending"].get("id") == on1.get("pending_id"),
          on2)
    check("resolving the one card clears the marker and turns the switch on",
          r.get("resolved_enabled") is True
          and resolved.get("waiting") is False
          and resolved.get("pending") is None, (r.get("resolved_enabled"),
                                                 resolved))
    check("OFF after the card resolved is immediate and asks no card",
          off.get("code") == 200 and off.get("waiting") is False
          and off.get("enabled") is False
          and off.get("message") == V.SWITCH_OFF_WORDS
          and r.get("cards_after_off") == 1
          and r.get("gate_calls_after_off") == 1, (off, r.get("cards_after_off")))
    check("the next ON raises exactly ONE new card, again with a real id",
          on3.get("code") == 202 and r.get("cards_after_on3") == 2
          and isinstance(on3.get("pending_id"), str)
          and bool(_PID.match(on3["pending_id"]))
          and on3.get("message") == V.SWITCH_ON_WORDS,
          (on3, r.get("cards_after_on3")))
    print(f"      fresh child marker before any request: "
          f"{r.get('initial_pending')} (truthy: {r.get('initial_pending_truthy')})")
    return len(FAILED)


def main() -> int:
    print(f"tree: {HERE}")
    print(f"backend: {BACKEND}")
    try:
        one()
    except Exception:                                     # noqa: BLE001
        FAILED.append("suite crashed")
        traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
