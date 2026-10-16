"""test_big_coder.py - the 30B coder's pause/restore contract, proved.

    python3 test_big_coder.py

WHAT THIS IS ABOUT

`jarvis_big_coder.py` is the one model on this PC that needs BOTH graphics
cards, so it can never sit beside the owner's two live lanes. The whole feature
is therefore a contract about ORDER and EVIDENCE, and this suite is what holds
it:

  1. it is OFF by default, and a start while it is off touches nothing at all;
  2. the pause is ANNOUNCED before anything on either card is touched, and the
     announcement names both lanes, their models and their contexts;
  3. BOTH lanes must be proved gone from /api/ps before the model is loaded -
     a lane that will not go means NOTHING is loaded;
  4. the model must load with ZERO spill at the measured context, or it is
     unloaded again and the lanes are put back;
  5. at NO point are the model and a lane model resident together (the trace
     below is checked step by step, not just at the end);
  6. stopping puts both lanes back EXACTLY: 11436 qwen3.5:9b at 196608 on the
     RTX 2060 and 11435 qwen3:8b at 16384 on the RTX 2080 SUPER, proved from
     /api/ps - right model, right context, zero spill;
  7. a lane that does not come back is REPORTED as a failure, never glossed.

Nothing in the suite touches the owner's PC: every /api/ps and every load is a
fake world, and the suite's own config folder is a temporary directory it
removes. It also checks the delivery half - the patch applies to the published
base, the module is in both SHIPPED lists, and apply-patches.ps1 stays ASCII.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing  # noqa: E402

import jarvis_big_coder as B  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   A whole PC, in a dictionary: three ports, their /api/ps, and a trace
# --------------------------------------------------------------------------

LANE_11436 = B.LANES[0]
LANE_11435 = B.LANES[1]


class World:
    """Three Ollama servers as dictionaries. `ports[port]` maps a model name
    to its /api/ps row, or is None when the server does not answer."""

    def __init__(self):
        self.ports = {
            11436: {LANE_11436.model: self.row(LANE_11436.model, LANE_11436.ctx)},
            11435: {LANE_11435.model: self.row(LANE_11435.model, LANE_11435.ctx)},
            11450: {},
        }
        self.trace = []          # every call, in order
        self.snapshots = []      # (what, coder_resident, lanes_resident)
        self.unload_refuses = set()   # ports whose unload silently does nothing
        self.load_ctx_override = {}   # port -> ctx the server really uses
        self.spill_bytes = 0          # bytes the coder loads with NOT in VRAM
        self.lane_spill = {}          # port -> bytes a LANE loads back with, NOT in VRAM

    @staticmethod
    def row(name, ctx, spill=0):
        return {"name": name, "context_length": ctx,
                "size": 10_000_000_000, "size_vram": 10_000_000_000 - spill}

    def snapshot(self, what):
        code = B.MODEL in (self.ports.get(11450) or {})
        lanes = sorted(n for p in (11436, 11435) for n in (self.ports.get(p) or {}))
        self.snapshots.append((what, code, lanes))

    # -- the module's four HTTP faces, all faked ---------------------------
    def ps(self, url):
        port = self._port(url)
        rows = self.ports.get(port, None)
        return None if rows is None else [dict(r) for r in rows.values()]

    def unload(self, url, model):
        port = self._port(url)
        self.trace.append(("unload", port, model))
        if port in self.unload_refuses:
            self.snapshot(f"unload {model} on {port} (refused)")
            return True
        (self.ports.get(port) or {}).pop(model, None)
        self.snapshot(f"unload {model} on {port}")
        return True

    def load(self, url, model, num_ctx):
        port = self._port(url)
        self.trace.append(("load", port, model, int(num_ctx)))
        ctx = int(self.load_ctx_override.get(port, num_ctx))
        spill = self.spill_bytes if model == B.MODEL else int(self.lane_spill.get(port, 0))
        self.ports.setdefault(port, {})[model] = self.row(model, ctx, spill)
        self.snapshot(f"load {model} on {port}")
        return True

    def known_on(self, url):
        port = self._port(url)
        if self.ports.get(port) is None:
            return None
        return port == 11450 or B.MODEL in (self.ports.get(port) or {})

    def server_start(self, port=B.BIG_PORT):
        self.trace.append(("server_start", int(port)))
        self.ports.setdefault(int(port), {})
        self.snapshot(f"server on {port}")
        return {"ok": True, "url": f"p{port}", "owned": True, "why": ""}

    def server_stop(self):
        self.trace.append(("server_stop",))
        self.ports[11450] = None
        self.snapshot("server stopped")
        return {"stopped": True, "why": ""}

    @staticmethod
    def _port(url):
        m = re.search(r"(\d+)$", str(url))
        return int(m.group(1)) if m else 0


class Wired:
    """Point the module at a World and remove it again afterwards."""

    def __init__(self, world, cfg):
        self.world, self.cfg = world, cfg
        self.saved = {}

    def __enter__(self):
        T = B
        for name, fn in (("ps", self.world.ps), ("unload", self.world.unload),
                         ("load", self.world.load), ("known_on", self.world.known_on),
                         ("server_start", self.world.server_start),
                         ("server_stop", self.world.server_stop),
                         ("config_dir", lambda: str(self.cfg)),
                         ("_url", lambda p: f"p{int(p)}")):
            self.saved[name] = getattr(T, name)
            setattr(T, name, fn)
        return self.world

    def __exit__(self, *exc):
        for name, fn in self.saved.items():
            setattr(B, name, fn)
        return False


class Verdict:
    def __init__(self, allowed, outcome=None, reason=""):
        self.allowed, self.outcome, self.reason = allowed, outcome, reason


def _fresh_switch(cfg):
    p = Path(cfg) / B.SWITCH_FILE
    if p.exists():
        p.unlink()


def _turn_on(cfg, *, gate=None):
    """The switch, through a card that is allowed (or not)."""
    return B.set_enabled(True, by="test", gate_check=gate or (lambda *a, **k: Verdict(True)))


# --------------------------------------------------------------------------
#   The states and the words
# --------------------------------------------------------------------------


def t_the_switch_is_off_by_default():
    """The whole feature rests on this: nothing is on until the owner says
    so, and a damaged file is OFF, never ON."""
    cfg = tempfile.mkdtemp(prefix="big-coder-cfg-")
    try:
        _fresh_switch(cfg)
        with Wired(World(), cfg):
            check("a machine that has never run this has the switch OFF", B.enabled() is False)
            Path(cfg, B.SWITCH_FILE).write_text("{ not json", encoding="utf-8")
            check("a damaged switch file is OFF, not on", B.enabled() is False)
            Path(cfg, B.SWITCH_FILE).write_text('{"on": false}', encoding="utf-8")
            check("an explicit false is OFF", B.enabled() is False)
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def t_the_card_names_both_lanes():
    """The announcement has to say WHICH two models stop and what they come
    back at - the owner is deciding whether to interrupt his own assistant."""
    words = B.card_text_start()
    check("the card names the model and both cards it needs",
          B.MODEL in words and "BOTH" in words)
    for lane in B.LANES:
        check(f"the card names {lane.model} at {lane.ctx} on the {lane.card}",
              lane.model in words and f"{lane.ctx:,}" in words and lane.card in words,
              words)
    check("the card says the context is the largest with no spill", "spill" in words)
    check("the card says nothing is downloaded", "downloaded" in words)


def t_turning_it_on_is_one_card_and_off_is_immediate():
    cfg = tempfile.mkdtemp(prefix="big-coder-cfg-")
    try:
        _fresh_switch(cfg)
        seen = []

        def refusing(action, detail, prompt):
            seen.append(action)
            return Verdict(False, "denied")

        with Wired(World(), cfg):
            code, out = B.set_enabled(True, by="test", gate_check=refusing)
            check("a refused card leaves the switch OFF", B.enabled() is False and out["ok"] is False)
            check("... and asks the gate with an EXISTING action name",
                  seen == [B.ACTION_ON] and B.ACTION_ON == "change_own_config", seen)
            code, out = _turn_on(cfg)
            check("an allowed card turns it ON", B.enabled() is True and out["changed"] is True)
            calls = []

            def never(action, detail, prompt):
                calls.append(action)
                return Verdict(True)

            code, out = B.set_enabled(False, by="test", gate_check=never)
            check("turning it OFF is immediate - the gate is never asked", calls == [])
            check("... and it really is off", B.enabled() is False and out["changed"] is True)
            code, out = B.set_enabled(False, by="test", gate_check=never)
            check("asking for OFF twice is not a change", out["changed"] is False)
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


# --------------------------------------------------------------------------
#   The contract
# --------------------------------------------------------------------------


def t_a_start_while_it_is_off_touches_nothing():
    cfg = tempfile.mkdtemp(prefix="big-coder-cfg-")
    try:
        _fresh_switch(cfg)
        w = World()
        with Wired(w, cfg):
            code, out = B.start(by="test", gate_check=lambda *a, **k: Verdict(True))
            check("a start while the switch is off is refused (409)", code == 409, str(out))
            check("... nothing was unloaded, loaded or started", w.trace == [], str(w.trace))
            check("... and both lanes are exactly as they were",
                  LANE_11436.model in w.ports[11436] and LANE_11435.model in w.ports[11435])
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def t_a_start_refuses_while_a_task_is_running():
    cfg = tempfile.mkdtemp(prefix="big-coder-cfg-")
    try:
        _fresh_switch(cfg)
        w = World()
        with Wired(w, cfg):
            _turn_on(cfg)
            code, out = B.start(by="test", gate_check=lambda *a, **k: Verdict(True),
                                tasks=lambda: [{"id": "t1"}])
            check("a running task stops the mode before anything is touched (409)",
                  code == 409, str(out))
            check("... and nothing was paused or loaded", w.trace == [], str(w.trace))
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def t_the_pause_is_announced_before_anything_is_touched():
    """The order is the contract. The announcement must come before the first
    unload - proved from the call trace, not from the wording."""
    cfg = tempfile.mkdtemp(prefix="big-coder-cfg-")
    try:
        _fresh_switch(cfg)
        w = World()
        published = []
        saved_pub = B._publish
        with Wired(w, cfg):
            _turn_on(cfg)
            # Every announcement leaves a mark IN the same trace as the unloads,
            # so "announced first" is a fact about one ordered list.
            B._publish = lambda kind, data: (published.append((kind, dict(data))),
                                             w.trace.append(("announce", data.get("state"))))
            try:
                code, out = B.start(by="test", gate_check=lambda *a, **k: Verdict(True))
            finally:
                B._publish = saved_pub
            check("the mode starts (200)", code == 200 and out.get("running") is True, str(out))
            kinds = [c[0] for c in w.trace]
            check("the pause is ANNOUNCED before the first unload",
                  "announce" in kinds and "unload" in kinds
                  and kinds.index("announce") < kinds.index("unload"), str(w.trace))
            check("... and before the both-cards server is even started",
                  kinds.index("announce") < kinds.index("server_start"), str(w.trace))
            check("... and the announcement says the lanes are pausing",
                  published and published[0][1].get("state") == "pausing", str(published))
            check("... and it carries the card's own words, lane by lane",
                  published and all(lane.model in published[0][1]["words"] for lane in B.LANES),
                  str(published))
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def t_the_pause_really_happens_before_the_load():
    cfg = tempfile.mkdtemp(prefix="big-coder-cfg-")
    try:
        _fresh_switch(cfg)
        w = World()
        with Wired(w, cfg):
            _turn_on(cfg)
            code, out = B.start(by="test", gate_check=lambda *a, **k: Verdict(True))
            order = [c[0] for c in w.trace]
            check("both lanes are unloaded before the model is loaded",
                  order.count("unload") == 2 and order.index("load") > max(
                      i for i, k in enumerate(order) if k == "unload"), str(w.trace))
            check("every step was proved from /api/ps, and the proof is in the answer",
                  len(out.get("paused", [])) == 2 and len(out.get("proof", [])) == 1, str(out))
            check("the model is loaded at the measured context, naming it",
                  any(c[0] == "load" and c[2] == B.MODEL and c[3] == B.NUM_CTX for c in w.trace),
                  str(w.trace))
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def t_the_model_is_never_resident_beside_a_lane():
    """THE check. Every fake call takes a snapshot; no snapshot may hold the
    coder and a lane model at the same time."""
    cfg = tempfile.mkdtemp(prefix="big-coder-cfg-")
    try:
        _fresh_switch(cfg)
        w = World()
        with Wired(w, cfg):
            _turn_on(cfg)
            B.start(by="test", gate_check=lambda *a, **k: Verdict(True))
            together = [(what, lanes) for what, code, lanes in w.snapshots if code and lanes]
            check("at NO point are the model and a lane model loaded together",
                  not together, str(together))
            check("the snapshots cover the whole start (a run that recorded nothing "
                  "would pass the check above for the wrong reason)",
                  len(w.snapshots) >= 4
                  and any("unload" in what for what, _c, _l in w.snapshots)
                  and any("load" in what for what, _c, _l in w.snapshots),
                  str(w.snapshots))
            check("after the start, the model is loaded and the lanes are not",
                  B.MODEL in w.ports[11450]
                  and not w.ports[11436] and not w.ports[11435])
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def t_a_lane_that_will_not_pause_stops_the_whole_start():
    """If the everyday lane will not unload, the mode must load NOTHING - it
    never runs beside a lane - and must put back what it did take."""
    cfg = tempfile.mkdtemp(prefix="big-coder-cfg-")
    try:
        _fresh_switch(cfg)
        w = World()
        w.unload_refuses = {11436}
        with Wired(w, cfg):
            _turn_on(cfg)
            code, out = B.start(by="test", gate_check=lambda *a, **k: Verdict(True))
            check("the start is refused (409), with the lane named",
                  code == 409 and LANE_11436.model in out.get("error", ""), str(out))
            check("NOTHING was loaded", not any(c[0] == "load" and c[2] == B.MODEL
                                                for c in w.trace), str(w.trace))
            check("the lane that WAS paused is put back",
                  any(c[0] == "load" and c[2] == LANE_11435.model for c in w.trace),
                  str(w.trace))
            check("both lanes are resident again", bool(w.ports[11436]) and bool(w.ports[11435]))
            check("the model is nowhere", not w.ports.get(11450))
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def t_a_load_that_spills_is_undone_and_the_lanes_come_back():
    """The measured promise is ZERO spill at 28,672. If this machine cannot
    give it both cards, the mode says so and leaves nothing behind."""
    cfg = tempfile.mkdtemp(prefix="big-coder-cfg-")
    try:
        _fresh_switch(cfg)
        w = World()
        w.spill_bytes = 200_000_000
        with Wired(w, cfg):
            _turn_on(cfg)
            code, out = B.start(by="test", gate_check=lambda *a, **k: Verdict(True))
            check("a spilled load is refused (503) and says why",
                  code == 503 and "spill" in out.get("error", ""), str(out))
            check("the model is unloaded again", not w.ports[11450])
            check("both lanes are back", bool(w.ports[11436]) and bool(w.ports[11435]))
            check("and the answer carries the restored lanes' proof",
                  len(out.get("restored", [])) == 2, str(out))
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def t_a_load_at_the_wrong_context_is_undone():
    cfg = tempfile.mkdtemp(prefix="big-coder-cfg-")
    try:
        _fresh_switch(cfg)
        w = World()
        w.load_ctx_override = {11450: 8192}
        with Wired(w, cfg):
            _turn_on(cfg)
            code, out = B.start(by="test", gate_check=lambda *a, **k: Verdict(True))
            check("the wrong context is refused (503), with both numbers in the reason",
                  code == 503 and "8192" in out.get("error", "")
                  and str(B.NUM_CTX) in out.get("error", ""), str(out))
            check("nothing is left loaded", not w.ports[11450])
            check("both lanes are back", bool(w.ports[11436]) and bool(w.ports[11435]))
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def t_stop_puts_both_lanes_back_exactly():
    """The owner's own two rows, proved from /api/ps: right model, right
    context, zero spill - and it goes through the /api/ps the module really
    reads, not a summary of it."""
    cfg = tempfile.mkdtemp(prefix="big-coder-cfg-")
    try:
        _fresh_switch(cfg)
        w = World()
        with Wired(w, cfg):
            _turn_on(cfg)
            code, out = B.start(by="test", gate_check=lambda *a, **k: Verdict(True))
            check("it is running after the start", code == 200 and B.running() is True)
            code, out = B.stop(by="test")
            check("stop reports success", code == 200 and out["ok"] is True, str(out))
            check("the model is gone from /api/ps", B.MODEL not in (w.ports[11450] or {}))
            check("the both-cards server this mode started is stopped", w.ports[11450] is None)
            for lane in (LANE_11435, LANE_11436):
                row = w.ports[lane.port].get(lane.model)
                check(f"port {lane.port} has {lane.model} back at {lane.ctx}",
                      row is not None and int(row["context_length"]) == lane.ctx, str(row))
                check(f"... and it is entirely in video memory (zero spill, port {lane.port})",
                      row is not None and row["size_vram"] == row["size"],
                      str(row))
            check("the answer says both models are back, with the two rows",
                  "qwen3.5:9b" in out["message"] and "qwen3:8b" in out["message"]
                  and len(out["restored"]) == 2, str(out))
            check("running() is now false - and it is read from /api/ps",
                  B.running() is False)
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def t_a_lane_that_does_not_come_back_is_reported():
    """The failure the feature must never hide: a lane that comes back at the
    wrong context, or with spill, is a 503 naming it."""
    cases = (
        ("wrong context", {"load_ctx_override": {11436: 2048}}, "2048"),
        ("spill", {"lane_spill": {11436: 500_000_000}}, "spill"),
    )
    for why, setting, expect in cases:
        cfg = tempfile.mkdtemp(prefix="big-coder-cfg-")
        try:
            _fresh_switch(cfg)
            w = World()
            with Wired(w, cfg):
                _turn_on(cfg)
                B.start(by="test", gate_check=lambda *a, **k: Verdict(True))
                check(f"(setup) the mode is running before the {why} case",
                      B.running() is True)
                for k, v in setting.items():
                    setattr(w, k, v)
                code, out = B.stop(by="test")
                check(f"a lane coming back with {why} is a 503, not a success",
                      code == 503 and out["ok"] is False, str(out))
                check(f"... and the reason names it ({why})",
                      expect in out.get("error", ""), str(out))
                check(f"... and the lane it belongs to is named too ({why})",
                      LANE_11436.model in out.get("error", ""), str(out))
        finally:
            shutil.rmtree(cfg, ignore_errors=True)


def t_status_changes_nothing():
    cfg = tempfile.mkdtemp(prefix="big-coder-cfg-")
    try:
        _fresh_switch(cfg)
        w = World()
        with Wired(w, cfg):
            _turn_on(cfg)
            before = Path(cfg, B.SWITCH_FILE).read_bytes()
            code, out = B.handle_get()
            check("GET /api/big-coder answers 200", code == 200)
            check("it reports the switch, the model and the context",
                  out["on"] is True and out["model"] == B.MODEL and out["num_ctx"] == B.NUM_CTX)
            check("it reports both lanes and their live state",
                  len(out["lanes"]) == 2
                  and out["lanes"][0]["loaded"] == [LANE_11436.model], str(out["lanes"]))
            check("it says what a start would do, in order",
                  len(out["what_a_start_would_do"]) == 3, str(out["what_a_start_would_do"]))
            check("it loaded nothing and unloaded nothing", w.trace == [], str(w.trace))
            check("... and did not rewrite the switch",
                  Path(cfg, B.SWITCH_FILE).read_bytes() == before)
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def t_the_one_post_answers_and_refuses_what_it_should():
    cfg = tempfile.mkdtemp(prefix="big-coder-cfg-")
    try:
        _fresh_switch(cfg)
        w = World()
        with Wired(w, cfg):
            code, out = B.handle_post("not a dict")
            check("a body that is not a JSON object is a 400", code == 400, str(out))
            code, out = B.handle_post({"nonsense": 1})
            check("a body naming neither `on` nor an action is a 400", code == 400, str(out))
            code, out = B.handle_post({"action": "start"}, by="test")
            check("start while off is the same refusal the route gives (409)",
                  code == 409 and out["ok"] is False, str(out))
            saved_gate = B._gate
            B._gate = lambda *a, **k: Verdict(True)
            try:
                code, out = B.handle_post({"on": True}, by="test")
            finally:
                B._gate = saved_gate
            check("`on` turns the switch on through the gate", code == 200
                  and out["changed"] is True and B.enabled() is True, str(out))
            code, out = B.handle_post({"action": "stop"}, by="test")
            check("stop while it is not running is a plain no-op, not an error",
                  code == 200 and out["changed"] is False, str(out))
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


# --------------------------------------------------------------------------
#   The delivery half: the patch, both lists, the base, ASCII
# --------------------------------------------------------------------------


def t_the_patch_applies_to_the_published_base():
    """The one thing a route patch must do: apply to the file the base folder
    carries, and leave a file that parses."""
    patch = HERE / "big-coder.patch"
    base = REPO / "jarvis-backend" / "jarvis_hud.py"
    if not patch.is_file():
        check("the patch is in backend/", False, str(patch))
        return
    if not base.is_file():
        skip("jarvis-backend/jarvis_hud.py is not in this checkout")
        return
    text = patch.read_text(encoding="utf-8")
    check("the patch targets jarvis_hud.py only", "--- a/jarvis_hud.py" in text
          and "--- a/" not in text.split("\n", 1)[1], text[:80])
    check("it adds BOTH routes (the read and the write)", text.count("/api/big-coder") == 2)
    added = "\n".join(line for line in text.splitlines() if line.startswith("+"))
    check("both blocks check origin and token, like every other route",
          added.count("_origin_ok(self)") == 2 and added.count("_token_ok(self)") == 2,
          f"origin={added.count('_origin_ok(self)')} token={added.count('_token_ok(self)')}")
    tmp = Path(tempfile.mkdtemp(prefix="big-coder-patch-"))
    try:
        shutil.copy2(base, tmp / "jarvis_hud.py")
        r = subprocess.run(["git", "apply", "-p1", str(patch)], cwd=str(tmp),
                           capture_output=True, text=True)
        if r.returncode != 0 and "not a git repository" in (r.stderr or ""):
            r = subprocess.run(["git", "apply", "-p1", "--unsafe-paths", str(patch)],
                               cwd=str(tmp), capture_output=True, text=True)
        check("git apply takes it against the published base", r.returncode == 0,
              (r.stderr or "").strip()[-300:])
        if r.returncode == 0:
            got = (tmp / "jarvis_hud.py").read_text(encoding="utf-8")
            check("... and the applied file carries the read route",
                  'if path == "/api/big-coder":' in got)
            check("... and the write route", 'if route == "/api/big-coder":' in got)
            check("... and it still parses as Python",
                  _parses(got))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _parses(text):
    import ast
    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False


def t_the_delivery_lists_carry_it():
    ps1 = REPO / "scripts" / "apply-patches.ps1"
    if not ps1.is_file():
        skip("scripts/apply-patches.ps1 is not in this checkout")
        return
    text = ps1.read_text(encoding="utf-8")
    order = re.findall(r"^\s*'([a-z0-9-]+\.patch)'", text, re.M)
    check("apply-patches.ps1 lists big-coder.patch", "big-coder.patch" in order)
    if "big-coder.patch" in order and "plugin-loader.patch" in order:
        check("... before plugin-loader.patch, which must stay last",
              order.index("big-coder.patch") < order.index("plugin-loader.patch"))
    check("... and lists jarvis_big_coder.py as shipped", "jarvis_big_coder.py" in text)
    check("apply-patches.ps1 is still pure ASCII",
          all(ord(c) < 128 for c in text),
          "a non-ASCII byte crept in - PowerShell 5.1 reads this by the code page")
    where = HERE / "_where.py"
    check("backend/_where.py lists it too", "jarvis_big_coder.py" in where.read_text(encoding="utf-8"))
    both = REPO / "jarvis-backend" / "jarvis_big_coder.py"
    check("the published base carries the same module, byte for byte",
          both.is_file() and both.read_bytes() == (HERE / "jarvis_big_coder.py").read_bytes(),
          str(both))


def t_the_patch_order_allow_lists_carry_it():
    """Each suite that pins the patch order must be told that this patch may
    come after its own - that is the trap that bit #248. There are FIVE, not
    four: test_gate_touches.py is the one that says plugin-loader.patch must
    stay last of all, and it has its own shortlist.

    This names THIS patch, which is no longer the newest one. The check below
    it asks the same question of whatever is newest, read from
    `_stack.order()` - so the trap this one was written for is caught for the
    next patch too, rather than once per release."""
    for name in ("test_devices.py", "test_referee.py", "test_gate_risk_rows.py",
                 "test_screen_attach.py", "test_gate_touches.py"):
        p = HERE / name
        if not p.is_file():
            skip(f"{name} is not in this checkout")
            continue
        text = p.read_text(encoding="utf-8")
        check(f"{name} allows big-coder.patch after its own", '"big-coder.patch"' in text
              or "'big-coder.patch'" in text)


def t_the_patch_order_allow_lists_carry_the_newest_patch_too():
    """The same trap, one release later: a patch appended after every other
    core patch must be named in all five order-pinning suites' allow-lists, or
    each of them goes red - which is exactly how #450's `backend` job failed on
    2026-10-15, with `initiative-payload.patch` (the phone's `checks` count on
    /api/initiative) missing from all five.

    Naming the FOUR FILES rather than "every file in backend" is on purpose.
    Four suites pin the newest core patch, read from `_stack.order()` rather
    than from a hand-written list - so the day another patch is appended last
    this check fails and says which files need the new name. `test_uncensored_optins.py`
    reads POSITION, not the newest entry, and says in its own words that
    asserting adjacency would assert a fact about the list's shape that nothing
    depends on; it is checked from the other side there, so it is not named here."""
    try:
        import _stack
        order = _stack.order()
    except Exception as exc:  # a checkout without backend/_stack.py
        skip(f"_stack.order() could not be read here: {exc}")
        return
    if not order or order[-1] != "plugin-loader.patch":
        skip("plugin-loader.patch is not last here, so the newest core patch "
             "cannot be worked out from the list")
        return
    newest = Path(order[-2]).name
    for name in ("test_devices.py", "test_referee.py", "test_gate_risk_rows.py",
                 "test_screen_attach.py", "test_gate_touches.py"):
        p = HERE / name
        if not p.is_file():
            skip(f"{name} is not in this checkout")
            continue
        text = p.read_text(encoding="utf-8")
        check(f"{name} allows {newest} (the last core patch) after its own",
              f'"{newest}"' in text or f"'{newest}'" in text)


def t_the_both_cards_server_is_the_one_this_mode_owns():
    """The server this mode starts must be a DIFFERENT process on a DIFFERENT
    port from both lanes, with CUDA_VISIBLE_DEVICES removed and OLLAMA_VULKAN
    set - the trap that silently moves a load onto the other card."""
    check("the mode's port is neither lane's",
          B.BIG_PORT not in [lane.port for lane in B.LANES], str(B.BIG_PORT))
    env = B._child_env(B.BIG_PORT)
    check("CUDA_VISIBLE_DEVICES is REMOVED, so Ollama sees both cards",
          "CUDA_VISIBLE_DEVICES" not in env)
    check("OLLAMA_VULKAN=0 is set, so CUDA is really used", env.get("OLLAMA_VULKAN") == "0")
    check("it listens on loopback only", env.get("OLLAMA_HOST") == f"127.0.0.1:{B.BIG_PORT}")
    check("and it may never reach the cloud", env.get("OLLAMA_NO_CLOUD") == "1")


def main() -> int:
    for fn in (t_the_switch_is_off_by_default, t_the_card_names_both_lanes,
               t_turning_it_on_is_one_card_and_off_is_immediate,
               t_a_start_while_it_is_off_touches_nothing,
               t_a_start_refuses_while_a_task_is_running,
               t_the_pause_is_announced_before_anything_is_touched,
               t_the_pause_really_happens_before_the_load,
               t_the_model_is_never_resident_beside_a_lane,
               t_a_lane_that_will_not_pause_stops_the_whole_start,
               t_a_load_that_spills_is_undone_and_the_lanes_come_back,
               t_a_load_at_the_wrong_context_is_undone,
               t_stop_puts_both_lanes_back_exactly,
               t_a_lane_that_does_not_come_back_is_reported,
               t_status_changes_nothing,
               t_the_one_post_answers_and_refuses_what_it_should,
               t_the_patch_applies_to_the_published_base,
               t_the_delivery_lists_carry_it,
               t_the_patch_order_allow_lists_carry_it,
               t_the_patch_order_allow_lists_carry_the_newest_patch_too,
               t_the_both_cards_server_is_the_one_this_mode_owns):
        fn()
    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED, {len(PASSED)} passed, {len(SKIPPED)} skipped")
        for name in FAILED:
            print(f"  - {name}")
        return 1
    print(f"all {len(PASSED)} checks passed, {len(SKIPPED)} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
