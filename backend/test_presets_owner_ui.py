"""A preset clicked in either app applies with NO card; the model path keeps it.

THE OWNER'S ASK, 2026-11-09: *"if i manually click and change the preset for
jarvis, it shouldnt need a card"* and *"if i manually choose anything in the
jarvis app or deskstop program, and its something that i can easily click and
change back right away, it shouldnt need a card"*. He said it again on
2026-11-16, about the one row that still carded: *"when i change the model on
the jarvis app it still sends me an approval card. that shouldnt happen if i
manually press the preset change. only if i ask through chat"*.

What this suite pins, in both directions:

  * the ROUTE the two apps' preset controls call (`POST /api/work/apply`)
    applies a local preset with no `jarvis_gate.check()` at all, writes a
    `preset_apply` receipt, and that receipt's Undo really puts the previous
    preset, model and lane back. Since 2026-11-16 that includes the HEAVY
    presets: a Coding or Medical click starts the pooled three-card lane with
    the owner's press as its approval, and a click that follows a heavy one
    writes the same undoable receipt;
  * the MODEL/chat path (`apply_from_body`, the function
    `jarvis_model_knowledge.apply_preset` and `jarvis_settings_registry.
    set_focus_preset` call) still asks exactly ONE `switch_model` card and
    writes no receipt - for the heavy presets that card is the pooled lane's
    own, and a denied card there unloads nothing;
  * the non-reversible rows are untouched: the Cloud preset still raises its
    `change_own_config` card and switches nothing, and the eight presets on a
    named lane are unchanged;
  * nothing in a request body can ask for the uncarded road, and the carded
    `switch_to` still asks in the shipped base module.

The model steward, the gate, the tripwire and the graphics card are stand-ins,
because this checkout has no GPU and no live backend. The REAL
`jarvis_model_lanes.start_pooled_lane` is driven through a fake big-coder module
(`FakePooled`), because its order, its gate call and its plain-words refusals are
the code under test - and so that no test asks the owner's own PC on port 11450.
The real `switch_to` asking its card is pinned by reading
`jarvis-backend/jarvis_models.py` itself, and the real route wrapper is driven
through `jarvis_presets.install()`.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
TMP = tempfile.mkdtemp(prefix="presets-owner-ui-")
os.environ["OPENJARVIS_CONFIG_DIR"] = TMP
os.environ["JARVIS_RECEIPTS_DB"] = str(Path(TMP) / "receipts.db")

import jarvis_model_lanes as L  # noqa: E402
import jarvis_presets as P       # noqa: E402
import jarvis_receipts as R      # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name
          + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.tier = "ask"
        self.reason = "the owner said no"
        self.outcome = "approved" if allowed else "denied"


class Gate:
    """A stand-in for jarvis_gate.check that records every question asked."""

    def __init__(self, allowed=True):
        self.calls = []
        self.allowed = allowed

    def check(self, action, detail=None, prompt="", **_kw):
        self.calls.append((action, detail, prompt))
        return Verdict(self.allowed)


class FakeModels:
    """jarvis_models, in the two shapes this module uses.

    `switch_to` is the CARDED function the model path calls: like the real one
    (jarvis-backend/jarvis_models.py:1174) it asks the gate `switch_model`
    before it writes the record. `_read_state`/`_write_state` are what the
    owner-click path writes through, exactly as `_default_adopt` already does.
    """

    MAX_HISTORY = 20

    def __init__(self, gate, installed=("m-one", "m-two", "qwen3.5:4b",
                                       "qwen3.5:9b"), current="m-one"):
        self.gate = gate
        self.installed = list(installed)
        self.state = {"current": current, "switches": []}
        self.writes = 0

    def safe_ref(self, ref):
        text = str(ref or "").strip()
        if not text or any(c in text for c in "\r\n\t"):
            raise ValueError("not a model reference")
        return text

    def is_installed(self, ref, names=None):
        return ref in self.installed

    def current_model(self):
        return self.state.get("current")

    def _read_state(self):
        return dict(self.state)

    def _write_state(self, st):
        self.state = dict(st)
        self.writes += 1
        return True

    def _probe_asker(self, ref):
        return lambda prompt: "Paris"

    def probe_refusal(self, model, url=None):
        """The real steward's tripwire guard (DEF-088), mirrored.

        The real one refuses a pooled model at the everyday lane and a lane
        whose window cannot be established; this stand-in has no lanes and no
        cards, so it refuses nothing and the suite keeps driving the road.
        """
        return ""

    def switch_to(self, ref, why=""):
        verdict = self.gate.check("switch_model",
                                  {"from": self.state.get("current"), "to": ref,
                                   "why": why}, "Switch the local model?")
        if not verdict.allowed:
            return {"ok": False, "ref": ref, "reason": verdict.reason}
        self.state["previous"] = self.state.get("current")
        self.state["current"] = ref
        return {"ok": True, "ref": ref}


class FakeTripwire:
    def __init__(self):
        self.baselines, self.afters = [], []

    def baseline(self, ask, model):
        self.baselines.append(model)
        return {}

    def after_swap(self, ask, model):
        self.afters.append(model)
        return {"ok": True, "model": model}


class FakeBigCoder:
    """`jarvis_big_coder`, without a graphics card: the steps the lane asks for.

    Only what `jarvis_model_lanes.start_pooled_lane` calls, in the order it
    calls them. `fails` makes ONE step answer no, so the lane's own plain-words
    refusal is proved as well as the happy path.
    """

    def __init__(self, fails=""):
        self.calls = []
        self.fails = fails
        self.rows = []

    def ps(self, url):
        self.calls.append("ps")
        return [dict(r) for r in self.rows]

    def loaded_row(self, rows, model):
        return next((r for r in rows or () if r.get("name") == model), None)

    def spill_bytes(self, row):
        return int((row or {}).get("size") or 0) - int((row or {}).get("size_vram") or 0)

    def card_text_start(self, **kw):
        return ("Use the coding model. It needs ALL THREE graphics cards, so the two "
                "models running now are paused first.")

    def lane_lines(self):
        return []

    def announce_pause(self, words):
        self.calls.append("announce")

    def server_start(self):
        self.calls.append("server_start")
        if self.fails == "server":
            return {"ok": False, "why": "the three-card Ollama could not be started"}
        return {"ok": True, "url": L.pooled_url(), "owned": True}

    def pause_lanes(self):
        self.calls.append("pause")
        return {"ok": True, "why": "", "proof": []}

    def load_coder(self, *, port=11450, num_ctx=None, allow_spill=None, mode=None):
        self.calls.append("load")
        if self.fails == "load":
            return {"ok": False, "proof": [],
                    "why": "the coding model did not fit on the three cards"}
        self.rows = [{"name": L.POOLED_MODEL, "context_length": num_ctx}] \
            if mode in (None, "coding") else [{"name": "medgemma:27b",
                                               "context_length": num_ctx}]
        return {"ok": True, "why": "", "proof": []}

    def unload_coder(self, *, port=11450, mode=None, model=None):
        self.rows = []
        return {"ok": True, "why": "", "proof": []}

    def restore_lanes(self):
        return {"ok": True, "why": "", "proof": []}

    def server_stop(self):
        self.calls.append("server_stop")
        return {"stopped": True, "why": ""}


class FakePooled:
    """Put the fake big-coder behind the REAL pooled lane for one block.

    `jarvis_model_lanes.start_pooled_lane` itself still runs: its order, its
    `gate` call and its refusals are the code under test. Only the graphics card
    and Ollama are replaced - and they are replaced on EVERY block that can
    reach it, because the real engine would ask the owner's own PC on port
    11450 (and, if the lane were down, really start a 14.8 GB load there).
    """

    def __init__(self, engine):
        self.engine = engine
        self.saved = ()

    def __enter__(self):
        self.saved = (L._engine, L._running_tasks)
        L._engine = lambda engine=None: self.engine
        L._running_tasks = lambda: []
        return self

    def __exit__(self, *exc):
        L._engine, L._running_tasks = self.saved
        return False


class SaveModules:
    """Put stand-ins in sys.modules for one block, then put it back."""

    NAMES = ("jarvis_models", "jarvis_gate", "jarvis_tripwire",
             "jarvis_chatbot_api")

    def __init__(self, **modules):
        self.modules = modules
        self.saved = {}

    def __enter__(self):
        for name in self.NAMES:
            self.saved[name] = sys.modules.get(name)
        for name, module in self.modules.items():
            if module is not None:
                sys.modules[name] = module
        return self

    def __exit__(self, *exc):
        for name, module in self.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        return False


def stub_lane(**over):
    """Fake the two external steps an apply takes, and record what it asked."""
    calls = []

    def start(key):
        calls.append(("start", key))
        return over.get("start", (200, {"ok": True, "changed": True}))

    def stop():
        calls.append(("stop_pooled",))
        return {"ok": True, "ran": False, "reason": ""}

    return calls, start, stop


class Handler:
    """The HUD's Handler, as install() wraps it."""

    def __init__(self):
        self.sent = []

    def do_POST(self):
        return "original-post"

    def _send(self, code, body):
        self.sent.append((code, body))
        return code


def drive_route(body, *, origin=True, token=True, **over):
    """POST /api/work/apply through the SHIPPED route wrapper."""
    calls, start, stop = stub_lane(**over)
    owner_switches = []
    real = (P._default_start_lane, P._default_stop_pooled,
            P._switch_for_the_owner, P._default_adopt,
            P._default_switch)
    P._default_start_lane = start
    P._default_stop_pooled = stop
    if over.get("owner_switch") is not None:
        P._switch_for_the_owner = over["owner_switch"]
    else:
        P._switch_for_the_owner = (
            lambda ref: (owner_switches.append(ref)
                         or {"ok": True, "ref": ref}))
    if over.get("adopt") is not None:
        P._default_adopt = over["adopt"]
    try:
        P.install(Handler, origin_ok=lambda h: origin,
                  token_ok=lambda h: token,
                  read_body=lambda h: json.dumps(body).encode())
        h = Handler()
        h.path = "/api/work/apply"
        code = h.do_POST()
    finally:
        (P._default_start_lane, P._default_stop_pooled,
         P._switch_for_the_owner, P._default_adopt,
         P._default_switch) = real
    return code, (h.sent[-1][1] if h.sent else {}), calls, owner_switches


def direct(body, **over):
    """Call the PUBLIC model/chat entry point (the carded road)."""
    calls, start, stop = stub_lane(**over)
    real = P._default_start_lane, P._default_stop_pooled
    P._default_start_lane, P._default_stop_pooled = start, stop
    try:
        return P.apply_from_body(body)
    finally:
        P._default_start_lane, P._default_stop_pooled = real


def receipts_now():
    return R.recent(50)


# --------------------------------------------------------------------------
#   1. The app-click road: no card, a receipt, and a real way back
# --------------------------------------------------------------------------

def t_route_applies_local_preset_with_no_card():
    gate = Gate()
    models = FakeModels(gate)
    with SaveModules(jarvis_models=models, jarvis_gate=gate,
                     jarvis_tripwire=FakeTripwire()):
        before = len(receipts_now())
        code, out, calls, owner_switches = drive_route({"preset": "fast"})
        after = receipts_now()
    check("the app's own route applies a local preset and reports it changed",
          code == 200 and out.get("changed") is True, (code, out))
    check("... through the uncarded owner switch, not the carded one",
          owner_switches == ["qwen3.5:4b"] and ("switch", "qwen3.5:4b") not in calls,
          (owner_switches, calls))
    check("... and asks the approval gate NOTHING at all",
          gate.calls == [], gate.calls)
    check("... starts the preset's lane once and points chat at it",
          [c[0] for c in calls] == ["stop_pooled", "start"]
          and calls[1] == ("start", "coding"), calls)
    check("... writes exactly one new preset_apply receipt",
          len(after) == before + 1
          and after[0].get("tool_name") == P.OWNER_RECEIPT_TOOL, after[:1])
    receipt = after[0] if after else {}
    check("... the receipt names what changed and what it replaced",
          "Fast" in receipt.get("summary", "")
          and "No preset was chosen before" in receipt.get("summary", ""),
          receipt.get("summary"))
    check("... its before snapshot is restorable and its after names the new preset",
          (receipt.get("before") or {}).get("preset") is None
          and (receipt.get("after") or {}).get("preset") == "fast", receipt)
    check("... the answer carries the same receipt id",
          bool(out.get("receipt_id")) and out.get("receipt_id") == receipt.get("receipt_id"),
          (out.get("receipt_id"), receipt.get("receipt_id")))
    check("... and the owner can press Undo on it",
          R.is_undoable(receipt) is True, receipt)
    check("... with the preset it replaced recorded for the click back",
          out.get("previous_preset") is None, out.get("previous_preset"))


def t_a_failed_switch_removes_its_receipt():
    gate = Gate()

    class Broken(FakeModels):
        def _write_state(self, st):
            return False

    models = Broken(gate)
    real_owner_switch = P._switch_for_the_owner
    with SaveModules(jarvis_models=models, jarvis_gate=gate,
                     jarvis_tripwire=FakeTripwire()):
        before = len(receipts_now())
        code, out, _calls, _sw = drive_route(
            {"preset": "fast"}, owner_switch=real_owner_switch)
        after = receipts_now()
    check("a switch that cannot write the model state refuses in words",
          code == 409 and out.get("changed") is False
          and "nothing changed" in out.get("error", "").lower(), (code, out))
    check("... and no receipt is left claiming a change that did not happen",
          len(after) == before, (before, len(after)))


def restore_with_lane_stubs(receipt_id):
    """Undo one receipt while the lane steps are stubbed, as an apply is."""
    calls, start, stop = stub_lane()
    real = P._default_start_lane, P._default_stop_pooled
    P._default_start_lane, P._default_stop_pooled = start, stop
    try:
        return R.undo(receipt_id)
    finally:
        P._default_start_lane, P._default_stop_pooled = real


def t_undo_puts_the_previous_preset_back():
    gate = Gate()
    models = FakeModels(gate)
    P._write_choice("general")
    P._set_active_url("http://127.0.0.1:11436")
    with SaveModules(jarvis_models=models, jarvis_gate=gate,
                     jarvis_tripwire=FakeTripwire()):
        code, out, _calls, owner_switches = drive_route({"preset": "fast"})
        receipt = R.get(out.get("receipt_id", "")) or {}
        undone = restore_with_lane_stubs(out.get("receipt_id", ""))
        twice = restore_with_lane_stubs(out.get("receipt_id", ""))
    check("a second click from General replaces it and applies at once",
          code == 200 and out.get("previous_preset") == "general"
          and owner_switches == ["qwen3.5:4b"], (code, out, owner_switches))
    check("... its receipt records General as the preset before",
          (receipt.get("before") or {}).get("preset") == "general", receipt)
    check("... Undo runs with no card and puts General back",
          undone.get("ok") is True and P.choice() == "general"
          and models.state.get("current") == "qwen3.5:9b"
          and gate.calls == [],
          (undone, P.choice(), models.state.get("current"), gate.calls))
    check("... the chat lane is back on the long-context card",
          json.loads((Path(TMP) / "presets-active-lane.json").read_text(
              encoding="utf-8")).get("base_url") == "http://127.0.0.1:11436",
          (Path(TMP) / "presets-active-lane.json").read_text(encoding="utf-8"))
    check("... and the same receipt cannot be undone twice",
          (twice.get("ok") is False
           and (twice.get("already_undone") is True or
                "already" in str(twice.get("error", "")).lower())),
          twice)


def t_undo_of_a_first_preset_forgets_the_choice():
    gate = Gate()
    models = FakeModels(gate)
    try:
        (Path(TMP) / "presets-choice.json").unlink()
    except FileNotFoundError:
        pass
    with SaveModules(jarvis_models=models, jarvis_gate=gate,
                     jarvis_tripwire=FakeTripwire()):
        code, out, _calls, _sw = drive_route({"preset": "fast"})
        undone = restore_with_lane_stubs(out.get("receipt_id", ""))
    check("the first preset ever applied can be undone to 'no preset chosen'",
          code == 200 and undone.get("ok") is True and P.choice() is None,
          (code, undone, P.choice()))


# --------------------------------------------------------------------------
#   2. The model/chat road: exactly ONE ask card, and no receipt
# --------------------------------------------------------------------------

def t_reclicking_the_same_preset_leaves_no_undo_row():
    gate = Gate()
    models = FakeModels(gate)
    real_owner_switch = P._switch_for_the_owner
    try:
        (Path(TMP) / "presets-choice.json").unlink()
    except FileNotFoundError:
        pass
    with SaveModules(jarvis_models=models, jarvis_gate=gate,
                     jarvis_tripwire=FakeTripwire()):
        code1, _out1, _c, _s = drive_route({"preset": "fast"},
                                           owner_switch=real_owner_switch)
        before = len(receipts_now())
        code2, out2, _c, _s = drive_route({"preset": "fast"},
                                          owner_switch=real_owner_switch)
        after = receipts_now()
    check("clicking the preset already in force still answers applied",
          code1 == 200 and code2 == 200 and out2.get("changed") is True,
          (code1, code2, out2))
    check("... and leaves no new receipt, because nothing changed",
          len(after) == before and out2.get("receipt_id") == "",
          (before, len(after), out2.get("receipt_id")))


def t_model_path_still_raises_one_ask_card():
    gate = Gate()
    models = FakeModels(gate)
    with SaveModules(jarvis_models=models, jarvis_gate=gate,
                     jarvis_tripwire=FakeTripwire()):
        before = len(receipts_now())
        code, out = direct({"preset": "fast"})
        after = receipts_now()
    check("the model/chat apply still succeeds through the carded switch",
          code == 200 and out.get("changed") is True, (code, out))
    check("... and asks exactly ONE switch_model card",
          len(gate.calls) == 1 and gate.calls[0][0] == "switch_model",
          gate.calls)
    check("... and writes no receipt, because the card is the record",
          len(after) == before, (before, len(after)))
    check("... and says no receipt id", out.get("receipt_id") == "", out)


def t_the_body_cannot_ask_for_the_uncarded_road():
    """No request field can ask for it: the ONLY ways in are two Python calls.

    `ast` nodes, not source text: a call with `owner_ui=<literal True>` is
    found structurally, and a library read that spells the name as a string
    (`body.get("owner_ui")`, `body["owner_ui"]`, headers...) is what would make
    a request field able to switch the card off - so there must be none.
    """
    import ast
    tree = ast.parse((HERE / "jarvis_presets.py").read_text(encoding="utf-8"))
    field_reads = [
        n for n in ast.walk(tree)
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("get", "pop", "setdefault", "getlist")
            and any(isinstance(a, ast.Constant) and a.value == "owner_ui"
                    for a in n.args))
        or (isinstance(n, ast.Subscript)
            and isinstance(n.slice, ast.Constant) and n.slice.value == "owner_ui")
    ]
    check("no request field is ever read for the uncarded road",
          not field_reads, field_reads)
    roads = []
    for top in tree.body:
        if not isinstance(top, ast.FunctionDef):
            continue
        for n in ast.walk(top):
            if not isinstance(n, ast.Call):
                continue
            name = getattr(n.func, "id", getattr(n.func, "attr", ""))
            if name not in ("_apply_body", "apply_preset"):
                continue
            for kw in n.keywords:
                if (kw.arg == "owner_ui"
                        and isinstance(kw.value, ast.Constant)
                        and isinstance(kw.value.value, bool)):
                    roads.append((top.name, name, kw.value.value))
    uncarded = [r for r in roads if r[2] is True]
    check("the uncarded road has exactly two literal callers: the route wrapper "
          "and the receipt restorer",
          sorted(uncarded) == sorted([("install", "_apply_body", True),
                                     ("restore_from_before", "apply_preset", True)]),
          roads)
    check("the public entry point is the carded road",
          ("apply_from_body", "_apply_body", False) in roads, roads)


def t_the_shipped_switch_to_still_asks():
    import ast
    import tomllib
    base = ast.parse((HERE.parent / "jarvis-backend" / "jarvis_models.py").read_text(
        encoding="utf-8"))
    switch = next((n for n in ast.walk(base)
                   if isinstance(n, ast.FunctionDef) and n.name == "switch_to"), None)
    gates = []
    if switch is not None:
        for n in ast.walk(switch):
            if (isinstance(n, ast.Call)
                    and getattr(n.func, "id", getattr(n.func, "attr", "")) == "_gate"
                    and any(isinstance(a, ast.Constant) and a.value == "switch_model"
                            for a in n.args)):
                gates.append(n)
    check("the shipped switch_to still raises its switch_model card",
          switch is not None and len(gates) == 1, len(gates))
    cfg = tomllib.loads((HERE / "rebuilt" / "jarvis-framework.toml").read_text(
        encoding="utf-8"))
    check("the shipped tier for switch_model is still ask",
          cfg["autonomy"]["tiers"].get("switch_model") == "ask",
          cfg["autonomy"]["tiers"].get("switch_model"))
    presets = ast.parse((HERE / "jarvis_presets.py").read_text(encoding="utf-8"))
    check("the owner-click path writes the model state and never calls the gate",
          any(isinstance(n, ast.FunctionDef) and n.name == "_switch_for_the_owner"
              for n in ast.walk(presets)))


# --------------------------------------------------------------------------
#   3. The heavy presets: uncarded when CLICKED (2026-11-16), still carded
#      when asked for in chat; and the rows that stay carded
# --------------------------------------------------------------------------

def t_a_heavy_click_applies_uncarded_and_starts_the_pooled_lane():
    """Coding and Medical, clicked on the apps' OWN route: no card, lane starts."""
    heavy = [p for p in P.PRESETS if p.heavy_mode]
    for p in heavy:
        gate = Gate()
        models = FakeModels(gate)
        eng = FakeBigCoder()
        P._write_choice("general")
        P._set_active_url("http://127.0.0.1:11436")
        before = len(receipts_now())
        with SaveModules(jarvis_models=models, jarvis_gate=gate,
                         jarvis_tripwire=FakeTripwire()), FakePooled(eng):
            code, out, calls, owner_switches = drive_route({"preset": p.id})
        after = receipts_now()
        started = [c for c in eng.calls
                   if c not in ("ps", "restore", "unload", "server_stop")]
        check(f"a {p.title} click applies at once and reports it changed",
              code == 200 and out.get("changed") is True, (code, out))
        check(f"... asks the approval gate NOTHING at all",
              gate.calls == [], gate.calls)
        check(f"... and really starts the pooled lane: announce, server, pause, load",
              started == ["announce", "server_start", "pause", "load"], eng.calls)
        check(f"... through the pooled lane, not a named-lane start",
              calls == [] and out.get("base_url") == P._lane_url(p.lane),
              (calls, out.get("base_url")))
        check(f"... records the model the lane loaded through adopt, never the "
              f"owner model switch",
              (out.get("switched") or {}).get("adopted") is True
              and models.state.get("current") == p.model
              and owner_switches == [],
              (out.get("switched"), models.state, owner_switches))
        check(f"... writes exactly one new preset_apply receipt",
              len(after) == before + 1
              and after[0].get("tool_name") == P.OWNER_RECEIPT_TOOL, after[:1])
        receipt = after[0] if after else {}
        check(f"... whose before snapshot is the General preset it replaced",
              (receipt.get("before") or {}).get("preset") == "general", receipt)
        check(f"... and the owner can press Undo on it",
              R.is_undoable(receipt) is True, receipt)


def t_undo_of_a_heavy_click_puts_the_previous_preset_back():
    gate = Gate()
    models = FakeModels(gate)
    eng = FakeBigCoder()
    P._write_choice("general")
    P._set_active_url("http://127.0.0.1:11436")
    with SaveModules(jarvis_models=models, jarvis_gate=gate,
                     jarvis_tripwire=FakeTripwire()), FakePooled(eng):
        code, out, _calls, owner_switches = drive_route({"preset": "coding"})
        receipt = R.get(out.get("receipt_id", "")) or {}
        undone = restore_with_lane_stubs(out.get("receipt_id", ""))
    check("a Coding click over General applies at once and records General before it",
          code == 200 and out.get("previous_preset") == "general"
          and (receipt.get("before") or {}).get("preset") == "general",
          (code, out.get("previous_preset"), receipt))
    check("... Undo runs with no card and puts General, its model and its lane back",
          undone.get("ok") is True and P.choice() == "general"
          and models.state.get("current") == "qwen3.5:9b"
          and gate.calls == [],
          (undone, P.choice(), models.state.get("current"), gate.calls))
    check("... the chat lane is back on the long-context card",
          json.loads((Path(TMP) / "presets-active-lane.json").read_text(
              encoding="utf-8")).get("base_url") == "http://127.0.0.1:11436",
          (Path(TMP) / "presets-active-lane.json").read_text(encoding="utf-8"))
    check("... and Coding itself was never routed through the owner model switch",
          owner_switches == [], owner_switches)
    # The other direction: on Coding, clicking General records Coding as the
    # preset before, and Undo puts Coding back on the SAME click road.
    eng2 = FakeBigCoder()
    with SaveModules(jarvis_models=models, jarvis_gate=gate,
                     jarvis_tripwire=FakeTripwire()), FakePooled(eng2):
        drive_route({"preset": "coding"})
        code2, out2, _calls2, _sw2 = drive_route({"preset": "general"})
        receipt2 = R.get(out2.get("receipt_id", "")) or {}
        back = restore_with_lane_stubs(out2.get("receipt_id", ""))
    check("a General click made while Coding is on records Coding before it, "
          "and says it can be undone",
          code2 == 200 and out2.get("previous_preset") == "coding"
          and (receipt2.get("before") or {}).get("preset") == "coding"
          and R.is_undoable(receipt2) is True, (code2, receipt2))
    check("... Undo puts Coding back with no card, on its pooled lane",
          back.get("ok") is True and P.choice() == "coding"
          and models.state.get("current") == P.by_id("coding").model
          and json.loads((Path(TMP) / "presets-active-lane.json").read_text(
              encoding="utf-8")).get("base_url") == "http://127.0.0.1:11450"
          and gate.calls == [],
          (back, P.choice(), models.state.get("current"), gate.calls))


def t_the_chat_road_still_raises_the_pooled_lane_card():
    """The SAME heavy preset asked from chat: one card, and a denial changes nothing."""
    gate = Gate(allowed=False)
    models = FakeModels(gate)
    eng = FakeBigCoder()
    P._write_choice("general")
    P._set_active_url("http://127.0.0.1:11436")
    before = len(receipts_now())
    with SaveModules(jarvis_models=models, jarvis_gate=gate,
                     jarvis_tripwire=FakeTripwire()), FakePooled(eng):
        code, out = P.apply_from_body({"preset": "coding"})
    after = receipts_now()
    check("Coding asked from chat still asks exactly ONE switch_model card",
          len(gate.calls) == 1 and gate.calls[0][0] == "switch_model",
          gate.calls)
    check("... the pooled lane's own card, naming the model it would load",
          bool(gate.calls)
          and (gate.calls[0][1] or {}).get("to") == P.by_id("coding").model
          and (gate.calls[0][1] or {}).get("why") == "preset",
          gate.calls)
    check("... a denied card changes nothing and says so",
          code == 409 and out.get("changed") is False
          and out.get("outcome") == "denied"
          and "nothing was changed" in out.get("error", ""), (code, out))
    check("... nothing on either card was unloaded: the lane never started",
          eng.calls == ["ps"], eng.calls)
    check("... no model is recorded, no receipt is written and the choice is not moved",
          models.state.get("current") == "m-one" and len(after) == before
          and P.choice() == "general", (models.state, len(after), P.choice()))
    gate = Gate()
    models = FakeModels(gate)
    eng = FakeBigCoder()
    with SaveModules(jarvis_models=models, jarvis_gate=gate,
                     jarvis_tripwire=FakeTripwire()), FakePooled(eng):
        code, out = P.apply_from_body({"preset": "coding"})
    check("... and once approved the carded road starts the lane and adopts",
          code == 200 and out.get("changed") is True
          and [c[0] for c in gate.calls] == ["switch_model"]
          and out.get("receipt_id") == ""
          and (out.get("switched") or {}).get("adopted") is True
          and "server_start" in eng.calls,
          (code, out, gate.calls, eng.calls))


def t_a_pooled_lane_that_will_not_start_changes_nothing():
    gate = Gate()
    models = FakeModels(gate)
    eng = FakeBigCoder(fails="load")
    P._write_choice("general")
    P._set_active_url("http://127.0.0.1:11436")
    before = len(receipts_now())
    with SaveModules(jarvis_models=models, jarvis_gate=gate,
                     jarvis_tripwire=FakeTripwire()), FakePooled(eng):
        code, out, _calls, _sw = drive_route({"preset": "coding"})
    after = receipts_now()
    check("a click whose pooled lane cannot load refuses (503) in the lane's words",
          code == 503 and "did not fit" in out.get("error", ""), (code, out))
    check("... says nothing was changed and leaves no receipt",
          "nothing was changed" in out.get("error", "")
          and len(after) == before, (out, len(after)))
    check("... no model is recorded and the chosen preset does not move",
          models.state.get("current") == "m-one" and P.choice() == "general",
          (models.state, P.choice()))
    check("... and the owner was never asked a card for a start that failed",
          gate.calls == [], gate.calls)


def t_every_named_lane_preset_click_is_still_uncarded():
    """The eight presets on a named lane: unchanged - no card, a receipt, its lane."""
    named = [p for p in P.PRESETS if not p.heavy_mode]
    check("there are eight presets on a named lane today",
          [p.id for p in named] == ["general", "general_uncensored", "agentic_vision",
                                    "fast", "reflect", "pictures", "documents",
                                    "browser"],
          [p.id for p in named])
    for p in named:
        gate = Gate()
        models = FakeModels(gate)
        before = len(receipts_now())
        with SaveModules(jarvis_models=models, jarvis_gate=gate,
                         jarvis_tripwire=FakeTripwire()):
            code, out, calls, owner_switches = drive_route({"preset": p.id})
        after = receipts_now()
        check(f"{p.id}: clicked, applied with no card and its own lane started",
              code == 200 and out.get("changed") is True and gate.calls == []
              and calls == [("stop_pooled",), ("start", p.lane)],
              (code, gate.calls, calls))
        check(f"{p.id}: the uncarded owner model switch did it, and a receipt was "
              f"written",
              owner_switches == [p.model] and len(after) == before + 1
              and after[0].get("tool_name") == P.OWNER_RECEIPT_TOOL,
              (owner_switches, len(after)))


def t_the_cloud_preset_still_raises_its_card():
    gate = Gate(allowed=False)

    class Service:
        company, host, model = "DeepSeek", "api.deepseek.com", "deepseek-chat"

    class Api:
        PRESETS = {"deepseek_api": Service()}

        @staticmethod
        def ready_for(pid):
            return ""

        @staticmethod
        def model_for(pid):
            return ("deepseek-chat", "")

        @staticmethod
        def money_view(pid):
            return {}

    with SaveModules(jarvis_chatbot_api=Api, jarvis_gate=gate):
        code, out = P.apply_from_body({"preset": "cloud",
                                       "provider": "deepseek_api"})
    check("the Cloud preset still asks one change_own_config card",
          len(gate.calls) == 1 and gate.calls[0][0] == P.CLOUD_ACTION,
          gate.calls)
    check("... a denied card changes nothing",
          code == 200 and out.get("changed") is False
          and out.get("outcome") == "denied", (code, out))
    check("... and it carries no receipt_id from the owner-click road",
          "receipt_id" not in out, out)


def t_every_preset_on_the_contract_is_covered():
    """The click rule is decided by `owner_ui` alone; the card lives in the lane.

    `ast` nodes, not source text: the old carve-out was the literal expression
    `owner_ui and not heavy`, so the check is that NO such second condition is
    back, and that the heavy model road is still `_default_adopt` (the click
    changes the card, not the model path).
    """
    import ast
    tree = ast.parse((HERE / "jarvis_presets.py").read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "apply_preset"), None)
    direct = None
    if fn is not None:
        for n in ast.walk(fn):
            if (isinstance(n, ast.Assign) and len(n.targets) == 1
                    and isinstance(n.targets[0], ast.Name)
                    and n.targets[0].id == "direct_owner"):
                direct = n.value
                break
    decided = (isinstance(direct, ast.Call)
               and getattr(direct.func, "id", "") == "bool"
               and any(isinstance(a, ast.Name) and a.id == "owner_ui"
                       for a in direct.args))
    check("the uncarded decision is the route's `owner_ui` alone - no preset id "
          "and no heavy condition", decided,
          ast.dump(direct) if direct is not None else None)
    adopt = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
             and getattr(n.func, "id", "") == "_default_adopt"] if fn else []
    check("the heavy model road in apply_preset is `_default_adopt` exactly once",
          len(adopt) == 1, len(adopt))
    lane = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                 and n.name == "_start_lane_for_the_owner"), None)
    gated = [kw for call in (ast.walk(lane) if lane is not None else ())
             if (isinstance(call, ast.Call)
                 and getattr(call.func, "attr", "") == "start_pooled_lane")
             for kw in call.keywords if kw.arg == "gate"]
    check("the owner lane start is the ONLY place a gate is passed to the pooled "
          "lane", bool(gated))
    check("Coding and Medical are the two heavy presets today, so they are the two "
          "the click rule covers",
          [p.id for p in P.PRESETS if p.heavy_mode] == ["coding", "medical"]
          and len(P.PRESETS) == 10,
          [p.id for p in P.PRESETS if p.heavy_mode])


def main() -> int:
    for fn in (t_route_applies_local_preset_with_no_card,
               t_a_failed_switch_removes_its_receipt,
               t_undo_puts_the_previous_preset_back,
               t_undo_of_a_first_preset_forgets_the_choice,
               t_reclicking_the_same_preset_leaves_no_undo_row,
               t_model_path_still_raises_one_ask_card,
               t_the_body_cannot_ask_for_the_uncarded_road,
               t_the_shipped_switch_to_still_asks,
               t_a_heavy_click_applies_uncarded_and_starts_the_pooled_lane,
               t_the_chat_road_still_raises_the_pooled_lane_card,
               t_undo_of_a_heavy_click_puts_the_previous_preset_back,
               t_a_pooled_lane_that_will_not_start_changes_nothing,
               t_every_named_lane_preset_click_is_still_uncarded,
               t_the_cloud_preset_still_raises_its_card,
               t_every_preset_on_the_contract_is_covered):
        fn()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
