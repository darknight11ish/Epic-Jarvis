"""A4: the persistent session safety latches, read-only in `/api/status`.

    python3 backend/test_status_latches.py

WHY THIS EXISTS. The HUD's fixed safety strip (`#hud-safety`, H4) could only
show the rush/outside-text EVIDENCE on a waiting card: the persistent latches
lived on the PC and `/api/status` did not carry them, so the strip went quiet
the moment no card was waiting - and across a backend restart nobody could tell
whether the session was still staying local. A4 (2026-10-23) exposes them,
read-only, on the route the HUD already reads. Nothing new is approved, no
route or permission is added, and a read must never clear a latch.

WHAT THIS CHECKS, and each one bites:

  1. **PERSISTENCE.** The taint latch is a SQLite row (`jarvis_gate.latch_taint`)
     and the rush latch is a small JSON file (`jarvis_content_risk.latch_rush`).
     Both are armed here and then each module is RELOADED FROM SCRATCH - module
     globals reset, which is what a process restart gives a fresh import - and
     asked again. A latch that lived only in a module global would read False
     here; the database/JSON copies must answer True/None-of-a-dict.
  2. **THE FIELD.** The committed published base HUD's own `/api/status` block is
     LIFTED OUT OF ITS FILE and executed as a function with a fake handler (the
     same shape `test_appearance.py` and `_where.hud_block` already use): the
     real `jarvis_gate` module and the real `jarvis_content_risk` module are
     passed in, so the answer carries `taint_latched` / `rush_latched` as true.
  3. **A READ CLEARS NOTHING.** The route is called twice; both latches are still
     armed afterwards. Structurally (with `ast`, not by pinning spelling) the
     route makes NO call to a clearing/approving/deciding function - so Rule 4's
     "the app never auto-approves anything" is not weakened by A4.
  4. **HONEST MISSING VALUES.** A missing gate module answers `null` ("the PC has
     not said"), never `false`; a gate that raises answers `true` (the gate's own
     fail-closed rule); a missing content-risk module answers `null`.
  5. **NO PROBE ON THE CALLER'S THREAD, unchanged.** With a warm `_STATUS_CACHE`
     the route calls no probe at all (DEF-002's property, re-proved here).

The two latches are cleared at the end, and every path (the approvals DB, the
content-risk file, the config folder and the audit log) is under this run's own
temporary folder, so the owner's real data is never read or written. Needs
nothing from the owner's PC: it runs against the committed `jarvis-backend/`
copy, so it runs in CI too.
"""
from __future__ import annotations

import ast
import importlib
import os
import shutil
import sys
import tempfile
import textwrap
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="jarvis-status-latches-"))
# Hermetic BEFORE either module is imported: the gate's approvals DB, the
# content-risk state file, the config folder and the audit log all go here.
os.environ["JARVIS_APPROVALS_DB"] = str(TMP / "approvals.db")
os.environ["JARVIS_CONTENT_RISK_STATE"] = str(TMP / "content-risk.json")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(TMP / "config")
os.environ["JARVIS_LOG_DIR"] = str(TMP / "logs")
(TMP / "config").mkdir(parents=True, exist_ok=True)

# The published base is a complete program: `jarvis_gate.py` and
# `jarvis_content_risk.py` import `jarvis_framework` beside them.
BASE = REPO / "jarvis-backend"
sys.path.insert(0, str(BASE))

import jarvis_content_risk as RISK  # noqa: E402
import jarvis_gate as GATE  # noqa: E402

HUD = BASE / "jarvis_hud.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (("\n      " + str(detail)) if (detail and not cond) else ""))


def _route_block() -> str:
    """The base HUD's own `/api/status` block, from its `if` to the 404 after it."""
    text = HUD.read_text(encoding="utf-8")
    start = text.index('        if path == "/api/status":')
    end = text.index("        return self._send(404", start)
    return text[start:end].rstrip("\n")


class FakeHandler:
    """Just enough of a BaseHTTPRequestHandler for this one route."""

    def __init__(self, path="/api/status"):
        self.path = path
        self.sent = []

    def _send(self, code, body, *args, **kwargs):
        self.sent.append((code, body))
        return code, body


class FakeGate:
    """A gate that cannot be asked: its read raises."""

    def taint_active(self):
        raise RuntimeError("the approvals store cannot be read")


_UNSET = object()


def _status(*, gate=_UNSET, cache=None, poll=None) -> dict:
    """Execute the LIFTED route once with fakes; return the JSON body it sent.

    `gate` is whatever the route's `jarvis_gate` name should be (the real
    module unless one is passed - `gate=None` really means "no gate module");
    `poll` counts calls to the cache poller. The rush half uses the real
    `jarvis_content_risk` already in `sys.modules` (the route imports it
    lazily), or whatever this test put there."""
    ns = {
        "_STATUS_CACHE": (cache if cache is not None else
                          {"jarvis": True, "ollama": False, "proxy": True,
                           "models": ["cached-model"], "polled_at": 1.0}),
        "_STATUS_LOCK": threading.Lock(),
        "_status_poll_once": poll or (lambda: None),
        "PROXY_FILE": TMP / "no-proxy.yml",
        "CONFIG_FILE": TMP / "no-config.toml",
        "_read_toml": lambda path: {},
        "ROUTING": False,
        "jarvis_router": None,
        "jarvis_injects_memory": lambda: False,
        "re": __import__("re"),
        "jarvis_gate": GATE if gate is _UNSET else gate,
    }
    source = ("def _route(self, path):\n"
              + textwrap.indent(textwrap.dedent(_route_block()), "    "))
    exec(compile(source, "<lifted /api/status>", "exec"), ns)   # noqa: S102 - fixture
    handler = FakeHandler()
    ns["_route"](handler, "/api/status")
    checks = [sent for sent in handler.sent if sent[0] == 200]
    if len(checks) != 1:
        raise AssertionError(f"the lifted route did not answer 200 exactly once: {handler.sent}")
    return checks[0][1]


def main() -> int:
    if not (HUD.is_file() and (BASE / "jarvis_gate.py").is_file()
            and (BASE / "jarvis_content_risk.py").is_file()):
        print("skip  the committed jarvis-backend copies are not here")
        return 0

    block = _route_block()

    # ---- 1. the latches persist, across a module reload ---------------------
    check("the taint latch starts clean", GATE.taint_active() is False)
    check("latch_taint arms it", GATE.latch_taint(minutes=5, why="A4 test") is True)
    check("... taint_active() says so", GATE.taint_active() is True)
    gate = importlib.reload(GATE)          # module globals reset = a fresh import
    check("the taint latch SURVIVES a restart (reload, not a process-local copy)",
          gate.taint_active() is True,
          "a latch held only in a module global would read False here")

    hit = RISK.RushHit(phrase="quick, before it expires", context="context", offset=0)
    check("latch_rush arms the rush latch",
          bool(RISK.latch_rush("A4-test-source", [hit], minutes=5))
          and RISK.rush_active() is not None)
    risk = importlib.reload(RISK)
    check("the rush latch SURVIVES a restart too",
          isinstance(risk.rush_active(), dict),
          "the JSON state file must answer; a module global would not")

    # ---- 2. the field is on /api/status, after that restart ------------------
    body = _status(gate=gate)
    check("the status answer carries taint_latched true after a restart",
          body.get("taint_latched") is True, body.get("taint_latched"))
    check("... and rush_latched true", body.get("rush_latched") is True,
          body.get("rush_latched"))
    check("... the ten existing keys are still there",
          all(key in body for key in
              ("routing", "jarvis_injects_memory", "budget", "jarvis", "ollama",
               "proxy", "models", "lanes", "default_model", "tools")))

    # ---- 3. a read clears nothing, and adds no approving call ---------------
    body2 = _status(gate=gate)
    check("a second read says the same",
          body2.get("taint_latched") is True and body2.get("rush_latched") is True,
          (body2.get("taint_latched"), body2.get("rush_latched")))
    check("... and clears neither latch",
          gate.taint_active() is True and isinstance(risk.rush_active(), dict),
          (gate.taint_active(), risk.rush_active() is not None))

    calls = {getattr(node.func, "id", None) or getattr(node.func, "attr", None)
             for node in ast.walk(ast.parse(textwrap.dedent(block)))
             if isinstance(node, ast.Call)}
    forbidden = {"clear_taint", "clear_rush", "confirm_auto", "decide_approval",
                 "latch_taint", "latch_rush", "approve", "deny"}
    check("the route makes NO clearing/approving/deciding call",
          not (forbidden & calls), sorted(forbidden & calls))
    check("... it calls the two read functions instead",
          {"taint_active", "rush_active"} <= calls, sorted(calls))
    check("... and it carries no approve/deny route string",
          all(word not in block for word in
              ("/api/approve", "/api/deny", "clear_taint", "clear_rush")))

    # ---- 4. honest missing values (null, never a false verdict) -------------
    body = _status(gate=FakeGate())
    check("a gate that cannot be read answers taint_latched true (fail closed)",
          body.get("taint_latched") is True, body.get("taint_latched"))
    body = _status(gate=None)
    check("no gate module answers null, never false",
          "taint_latched" in body and body.get("taint_latched") is None,
          body.get("taint_latched"))
    saved = sys.modules.get("jarvis_content_risk")
    try:
        sys.modules["jarvis_content_risk"] = None    # import raises ImportError
        body = _status(gate=gate)
        check("no content-risk module answers rush_latched null, never false",
              "rush_latched" in body and body.get("rush_latched") is None,
              body.get("rush_latched"))
    finally:
        if saved is None:
            sys.modules.pop("jarvis_content_risk", None)
        else:
            sys.modules["jarvis_content_risk"] = saved

    # ---- 5. no probe on the caller's thread while the cache is warm ---------
    polls = []
    _status(gate=gate, poll=lambda: polls.append(1))
    check("a warm cache answers with NO probe on the caller's thread",
          polls == [], polls)

    # ---- after clearing, the fields follow the latch (not something sticky) --
    gate.clear_taint()
    risk.clear_rush()
    body = _status(gate=gate)
    check("after clearing, both fields say false",
          body.get("taint_latched") is False and body.get("rush_latched") is False,
          (body.get("taint_latched"), body.get("rush_latched")))

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
