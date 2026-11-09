"""A preset clicked in either app applies with NO card; the model path keeps it.

THE OWNER'S ASK, 2026-11-09: *"if i manually click and change the preset for
jarvis, it shouldnt need a card"* and *"if i manually choose anything in the
jarvis app or deskstop program, and its something that i can easily click and
change back right away, it shouldnt need a card"*.

What this suite pins, in both directions:

  * the ROUTE the two apps' preset controls call (`POST /api/work/apply`)
    applies a local, non-heavy preset with no `jarvis_gate.check()` at all,
    writes a `preset_apply` receipt, and that receipt's Undo really puts the
    previous preset, model and lane back;
  * the MODEL/chat path (`apply_from_body`, the function
    `jarvis_model_knowledge.apply_preset` and `jarvis_settings_registry.
    set_focus_preset` call) still asks exactly ONE `switch_model` card and
    writes no receipt;
  * the non-reversible rows are untouched: the heavy Coding preset still goes
    through the pooled lane's own asking start, and the Cloud preset still
    raises its `change_own_config` card and switches nothing;
  * nothing in a request body can ask for the uncarded road, and the carded
    `switch_to` still asks in the shipped base module.

The model steward, the gate and the tripwire are stand-ins, because this
checkout has no graphics card and no live backend. The real `switch_to` asking
its card is pinned by reading `jarvis-backend/jarvis_models.py` itself, and the
real route wrapper is driven through `jarvis_presets.install()`.
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
#   3. The non-reversible rows are untouched
# --------------------------------------------------------------------------

def t_the_heavy_preset_still_goes_through_its_own_asking_start():
    gate = Gate()
    models = FakeModels(gate)
    adopt_calls = []
    refused = (200, {"ok": False, "changed": False, "outcome": "denied",
                     "message": "Not started - nothing was paused and nothing "
                                "was loaded."})
    with SaveModules(jarvis_models=models, jarvis_gate=gate,
                     jarvis_tripwire=FakeTripwire()):
        code, out, calls, owner_switches = drive_route(
            {"preset": "coding"}, start=refused)
    check("Coding still goes through its pooled lane's OWN asking start",
          calls == [("start", "pooled")], calls)
    check("... the route never uses the uncarded switch for it",
          owner_switches == [], owner_switches)
    check("... a denied card there changes nothing and says so",
          code == 409 and out.get("outcome") == "denied"
          and "nothing was changed" in out.get("error", ""), (code, out))
    with SaveModules(jarvis_models=models, jarvis_gate=gate,
                     jarvis_tripwire=FakeTripwire()):
        code, out, calls, owner_switches = drive_route(
            {"preset": "coding"},
            adopt=lambda ref: (adopt_calls.append(ref) or {"ok": True, "ref": ref}))
    check("... and once its card is approved it records through adopt, not the "
          "owner switch",
          code == 200 and adopt_calls == ["qwen3-coder-30b-a3b-ud-q3-k-xl"]
          and owner_switches == [], (code, adopt_calls, owner_switches))


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
    """The rule is decided by `heavy_mode`, not by a list of ids."""
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
    decided = isinstance(direct, ast.BoolOp) and isinstance(direct.op, ast.And) and (
        any(isinstance(v, ast.Call) and getattr(v.func, "id", "") == "bool"
            and any(isinstance(a, ast.Name) and a.id == "owner_ui" for a in v.args)
            for v in direct.values)
        and any(isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.Not)
                and isinstance(v.operand, ast.Name) and v.operand.id == "heavy"
                for v in direct.values))
    check("the uncarded decision is `owner_ui and not heavy`", decided)
    check("Coding is the one heavy preset today, so it is the one kept carded",
          [p.id for p in P.PRESETS if p.heavy_mode] == ["coding"]
          and len(P.PRESETS) == 9,
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
               t_the_heavy_preset_still_goes_through_its_own_asking_start,
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
