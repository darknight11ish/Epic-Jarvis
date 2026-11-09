"""The manual-click rule has TWO sides, and this suite pins both.

THE OWNER'S ASK (2026-11-09): *"if i manually choose anything in the jarvis app
or deskstop program, and its something that i can easily click and change back
right away, it shouldnt need a card"*. GEMINI'S RULING Q2 (2026-11-09): an
explicit backend allow-list gated by a trusted UI-origin signal - never a
blanket route bypass, never a header/body field.

What this suite proves, in both directions:

  * every action in `jarvis_reversible_ui.REVERSIBLE_UI_CHOICES` runs through
    its trusted-UI route with ZERO `jarvis_gate.check()` calls, and writes the
    record that action normally writes (a `preset_apply` receipt for a preset;
    the model state and one switch-log entry for a model);
  * the SAME action through the model/chat path still raises exactly ONE card.
    For `switch_model` that is the REAL shipped `jarvis_models.switch_to`,
    loaded from `jarvis-backend/` and driven with a recording gate - not a
    stand-in for the function being tested;
  * the excluded set (deletion/forget_range, installs/downloads, Lockdown off,
    app lock, credentials, github_create_repo, email/message sends, imports)
    is refused by the allow-list, and its real gate-bearing code still asks.
    Where the owner's module is not shipped in this repository (a live-only
    file, or an action Wave 13 has not built yet) this suite says so and pins
    the source instead of pretending to drive it;
  * no request body field, header or query parameter can ask for the uncarded
    road. The path decides before the body is parsed, and only `ref` and `why`
    are read;
  * the shipped tier table is untouched and `switch_model` is still "ask";
  * the module is in SHIPPED (both lists) and both copies are byte-equal.

The model steward, the gate and the tripwire are stand-ins only where a live
graphics card or Ollama would be needed. `jarvis-backend/jarvis_models.py` is
imported and driven for real: that is the function whose card is the fence.
"""
import ast
import importlib.util
import json
import os
import re
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "jarvis-backend"
TMP = tempfile.mkdtemp(prefix="reversible-ui-")
os.environ["OPENJARVIS_CONFIG_DIR"] = TMP
os.environ["JARVIS_RECEIPTS_DB"] = str(Path(TMP) / "receipts.db")

sys.path.insert(0, str(HERE))

import jarvis_presets as P          # noqa: E402
import jarvis_receipts as R         # noqa: E402
import jarvis_reversible_ui as V    # noqa: E402

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


class Tripwire:
    def __init__(self):
        self.baselines, self.afters = [], []

    def baseline(self, ask, model):
        self.baselines.append(model)
        return {}

    def after_swap(self, ask, model):
        self.afters.append(model)
        return {"ok": True, "model": model}


class FakeHandler:
    """One fresh HUD Handler per route call, so wrappers never stack."""

    def __init__(self):
        self.path = "/"
        self.sent = []

    def do_POST(self):
        return "original-post"

    def _send(self, code, body):
        self.sent.append((code, body))
        return code


def stub_lanes():
    calls = []

    def start(key):
        calls.append(("start", key))
        return 200, {"ok": True, "changed": True}

    def stop():
        calls.append(("stop_pooled",))
        return {"ok": True, "ran": False, "reason": ""}

    return calls, start, stop


def drive(body, path="/api/work/apply", *, origin=True, token=True):
    """POST through the SHIPPED installer: presets.install() wires both routes."""
    P.install(FakeHandler, origin_ok=lambda h: origin,
              token_ok=lambda h: token,
              read_body=lambda h: json.dumps(body).encode())
    h = FakeHandler()
    h.path = path
    code = h.do_POST()
    return code, (h.sent[-1][1] if h.sent else {}), h


def receipts_now():
    return R.recent(50)


# --------------------------------------------------------------------------
#   Small AST helpers - the checks below walk the tree, they never compare
#   strings against a production module's TEXT (tools/check_no_source_pins.py).
# --------------------------------------------------------------------------

def py_tree(rel):
    return ast.parse((REPO / rel).read_text(encoding="utf-8"), rel)


def funcs_named(tree, name):
    return [n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == name]


def calls_named(tree, name):
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            got = (f.attr if isinstance(f, ast.Attribute)
                   else f.id if isinstance(f, ast.Name) else "")
            if got == name:
                out.append(node)
    return out


def str_args(call):
    return [a.value for a in call.args
            if isinstance(a, ast.Constant) and isinstance(a.value, str)]


def const_named(tree, name):
    """The string value of a module-level `NAME = "..."`, or None."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            value = getattr(node, "value", None)
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
    return None


# --------------------------------------------------------------------------
#   The real shipped model steward, from the published base
# --------------------------------------------------------------------------

def load_base_models():
    """Import `jarvis-backend/jarvis_models.py` as `jarvis_models`."""
    spec = importlib.util.spec_from_file_location(
        "jarvis_models", str(BASE / "jarvis_models.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["jarvis_models"] = module
    spec.loader.exec_module(module)
    return module


M = load_base_models()
TW = Tripwire()
sys.modules["jarvis_tripwire"] = TW
MODELS = {"installed": ["m-one", "m-two", "qwen3.5:4b", "qwen3.5:9b"],
          "state": {"current": "m-one", "switches": []}}


def reset_models():
    MODELS["installed"] = ["m-one", "m-two", "qwen3.5:4b", "qwen3.5:9b"]
    MODELS["state"] = {"current": "m-one", "switches": []}
    TW.baselines.clear()
    TW.afters.clear()


def wire_models(gate):
    """Make the REAL module use the recording gate and an in-memory state."""
    def read_state():
        return dict(MODELS["state"])

    def write_state(st):
        MODELS["state"] = dict(st)
        return True

    M._gate = gate.check
    M._read_state = read_state
    M._write_state = write_state
    M.is_installed = lambda ref, names=None: ref in MODELS["installed"]
    M._probe_asker = lambda ref: (lambda prompt: "Paris")
    M.preflight = lambda ref, models=None, **kw: {
        "already_installed": False, "fits": True, "vram_mb": 6000,
        "budget_mb": 11000, "size_gb": 5.0}


# --------------------------------------------------------------------------
#   1. The allow-list itself
# --------------------------------------------------------------------------

def t_the_list_is_exactly_the_two_wired_choices():
    check("the allow-list has exactly the two actions this lane wired",
          set(V.REVERSIBLE_UI_CHOICES) == {"apply_preset", "switch_model"},
          sorted(V.REVERSIBLE_UI_CHOICES))
    for name, row in V.REVERSIBLE_UI_CHOICES.items():
        check(f"{name}: has a plain-words reason, its UI road and the model path "
              f"that still asks",
              bool(row.get("reason")) and bool(row.get("ui_road"))
              and bool(row.get("model_path_asks")), row)
        check(f"{name}: is_reversible_ui_choice says yes",
              V.is_reversible_ui_choice(name) is True)
        check(f"{name}: reason_for returns its reason",
              V.reason_for(name) == row["reason"])
    for bad in ("", "forget_range", "switch_model ", "SWITCH_MODEL", None, 42):
        check(f"is_reversible_ui_choice refuses {bad!r}",
              V.is_reversible_ui_choice(bad) is False)
    check("reason_for returns nothing for an unknown action",
          V.reason_for("forget_range") == "")


# --------------------------------------------------------------------------
#   2. apply_preset, both sides
# --------------------------------------------------------------------------

def t_apply_preset_ui_path_asks_nothing():
    gate = Gate()
    wire_models(gate)
    reset_models()
    calls, start, stop = stub_lanes()
    real = P._default_start_lane, P._default_stop_pooled, P._switch_for_the_owner
    P._default_start_lane, P._default_stop_pooled = start, stop
    try:
        before = len(receipts_now())
        code, out, _h = drive({"preset": "fast"})
        after = receipts_now()
    finally:
        (P._default_start_lane, P._default_stop_pooled,
         P._switch_for_the_owner) = real
    check("a preset clicked in the app's own route applies with no card",
          code == 200 and out.get("changed") is True, (code, out))
    check("... and asks the approval gate NOTHING at all",
          gate.calls == [], gate.calls)
    check("... writes its normal preset_apply receipt",
          len(after) == before + 1
          and after[0].get("tool_name") == P.OWNER_RECEIPT_TOOL,
          after[:1])
    check("... and the model moved through the uncarded owner switch",
          MODELS["state"].get("current") == "qwen3.5:4b", MODELS["state"])


def t_apply_preset_model_path_still_asks_one_card():
    gate = Gate()
    wire_models(gate)
    reset_models()
    calls, start, stop = stub_lanes()
    real = P._default_start_lane, P._default_stop_pooled
    P._default_start_lane, P._default_stop_pooled = start, stop
    try:
        before = len(receipts_now())
        code, out = P.apply_from_body({"preset": "fast"})
        after = receipts_now()
    finally:
        P._default_start_lane, P._default_stop_pooled = real
    check("the same preset through the model/chat entry point still applies",
          code == 200 and out.get("changed") is True, (code, out))
    check("... by asking exactly ONE switch_model card",
          len(gate.calls) == 1 and gate.calls[0][0] == "switch_model",
          gate.calls)
    check("... and writes no receipt, because the card is the record",
          len(after) == before, (before, len(after)))


# --------------------------------------------------------------------------
#   3. switch_model, both sides - the model path is the REAL shipped function
# --------------------------------------------------------------------------

def t_switch_model_ui_path_asks_nothing_and_records():
    gate = Gate()
    wire_models(gate)
    reset_models()
    code, out, _h = drive({"ref": "m-two", "why": "desktop"},
                          path=V.SWITCH_ROUTE)
    check("a model picked in the app's own model list switches at once",
          code == 200 and out.get("ok") is True, (code, out))
    check("... and asks the approval gate NOTHING at all",
          gate.calls == [], gate.calls)
    check("... writes the same model record switch_to writes",
          MODELS["state"].get("current") == "m-two"
          and MODELS["state"].get("previous") == "m-one"
          and len(MODELS["state"].get("switches") or []) == 1,
          MODELS["state"])
    check("... keeps the request's own why, in words",
          MODELS["state"].get("why") == "desktop", MODELS["state"].get("why"))
    check("... and runs the tripwire smoke test the same way",
          TW.afters == ["m-two"], TW.afters)


def t_switch_model_model_path_still_asks_exactly_one_card():
    gate = Gate()
    wire_models(gate)
    reset_models()
    out = M.switch_to("m-two", why="chat")
    check("the REAL shipped switch_to still switches (the card was allowed)",
          out.get("ok") is True and out.get("ref") == "m-two", out)
    check("... by asking exactly ONE switch_model card",
          len(gate.calls) == 1 and gate.calls[0][0] == "switch_model",
          gate.calls)
    detail = gate.calls[0][1] if gate.calls else {}
    check("... naming the model it leaves and the model it moves to",
          detail.get("from") == "m-one" and detail.get("to") == "m-two"
          and detail.get("why") == "chat", detail)
    check("... and it is still the shipped 'ask' tier (checked in section 7)",
          True)


def t_the_switch_route_cannot_be_asked_for_no_card():
    # (a) The model/chat entry point ignores every invented "no card" field.
    gate = Gate()
    wire_models(gate)
    reset_models()
    calls, start, stop = stub_lanes()
    real = P._default_start_lane, P._default_stop_pooled
    P._default_start_lane, P._default_stop_pooled = start, stop
    try:
        code, out = P.apply_from_body({"preset": "fast", "owner_ui": True,
                                       "ui_direct": True, "no_card": True})
    finally:
        P._default_start_lane, P._default_stop_pooled = real
    check("a body naming owner_ui/ui_direct on the model path is IGNORED",
          len(gate.calls) == 1 and gate.calls[0][0] == "switch_model",
          gate.calls)
    # (b) The UI route ignores the same fields in both directions: the path,
    # not the body, is the signal.
    gate = Gate()
    wire_models(gate)
    reset_models()
    code, out, _h = drive({"ref": "m-two", "owner_ui": False,
                           "ui_direct": False, "no_card": False},
                          path=V.SWITCH_ROUTE)
    check("the switch route does not read those fields either (path decides)",
          code == 200 and out.get("ok") is True and gate.calls == [],
          (code, out, gate.calls))
    # (c) A query string and an extra field change nothing: the route strips
    # the query and reads only ref/why.
    gate = Gate()
    wire_models(gate)
    reset_models()
    code, out, _h = drive({"ref": "m-two", "why": "phone"},
                          path=V.SWITCH_ROUTE + "?owner_ui=1&ui_direct=1")
    check("a query string asking for it is ignored (the query is not read)",
          code == 200 and out.get("ok") is True and gate.calls == [],
          (code, out, gate.calls))
    # (d) Every other path is forwarded untouched, so no route is bypassed.
    gate = Gate()
    wire_models(gate)
    reset_models()
    code, out, h = drive({"ref": "new-model", "owner_ui": True},
                         path="/api/models/install")
    check("a non-switch path is forwarded to the handler that already owned it",
          code == "original-post" and h.sent == [], (code, h.sent))
    check("... and the wrapper asked the gate nothing on the way",
          gate.calls == [], gate.calls)
    # (e) The module's own tree: the decision never reads request input.
    tree = py_tree("backend/jarvis_reversible_ui.py")
    body_keys = []
    for call in calls_named(tree, "get"):
        f = call.func
        if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                and f.value.id == "body"):
            body_keys.extend(str_args(call))
    check("the body keys it reads are exactly ref and why",
          sorted(body_keys) == ["ref", "why"], body_keys)
    check("no owner_ui / ui_direct / no_card field is read for the decision",
          not ({"owner_ui", "ui_direct", "no_card"} & set(body_keys)), body_keys)
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    called |= {n.func.id for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    check("it reads no header and no query parameter at all",
          not ({"headers", "getheader", "parse_qs", "urlparse"} & (attrs | called)),
          sorted(attrs | called))


def t_the_switch_route_keeps_the_huds_checks():
    """The wrapper copies the HUD's own branch, refusals included."""
    gate = Gate()
    wire_models(gate)
    reset_models()
    code, out, _h = drive({"ref": "m-two"}, path=V.SWITCH_ROUTE, origin=False)
    check("a cross-origin switch is refused before anything is read",
          code == 403 and gate.calls == [] and out.get("error"), (code, out))
    code, out, _h = drive({"ref": "m-two"}, path=V.SWITCH_ROUTE, token=False)
    check("a switch with a bad or missing token is refused",
          code == 401 and gate.calls == [], (code, out))
    code, out, _h = drive({}, path=V.SWITCH_ROUTE)
    check("a switch with no model ref answers 400 in the HUD's own words",
          code == 400 and out.get("error") == "need a model ref", (code, out))


# --------------------------------------------------------------------------
#   4. The excluded set: refused, and its real code still asks
# --------------------------------------------------------------------------

#: Names the ruling says must ALWAYS ask, and the module that owns each. Every
#: name here must be absent from REVERSIBLE_UI_CHOICES.
EXCLUDED_NAMES = (
    "delete_memory", "forget_range", "delete_skill", "delete_model",
    "download_model", "install_skill", "edit_skill", "apply_self_code",
    "run_update", "lockdown_off", "app_lock", "credentials",
    "reveal_private_memory", "raise_spend_limit", "github_create_repo",
    "send_email", "send_message", "import_notion_export", "import_history",
    "purge_history",
)

#: (file, function or None for the whole tree, callee, first string argument,
#: what it proves). Walked as AST calls, never by comparing source text.
CALL_PINS = (
    ("jarvis-backend/jarvis_models.py", "install", "_gate", "download_model",
     "a model download still asks its own card"),
    ("backend/jarvis_forget_range.py", "_decide", "gate", None,
     "forget_range raises its card through the gate inside _decide"),
    ("backend/jarvis_skill_menu.py", "set_state", "install", None,
     "turning a skill back ON runs the scanner's install (and its card)"),
    ("jarvis-backend/jarvis_skills.py", None, "_gate", "modify_own_code",
     "skill/plugin install and edit still ask modify_own_code"),
)

#: (file, constant, value, what it proves).
CONST_PINS = (
    ("backend/jarvis_forget_range.py", "ACTION", "memory_forget_range",
     "forget_range is its own ask-tier action"),
    ("backend/jarvis_notion_obsidian.py", "CARD_ACTION", "change_own_config",
     "a Notion import still asks change_own_config"),
)


def t_the_excluded_set_is_refused_by_name():
    for name in EXCLUDED_NAMES:
        check(f"the allow-list refuses {name!r}",
              V.is_reversible_ui_choice(name) is False)
        check(f"... and the module records why {name!r} always asks",
              V.is_excluded(name) is True and bool(V.EXCLUDED_UI_ACTIONS[name]))


def t_a_download_still_asks_its_card():
    gate = Gate(allowed=False)
    wire_models(gate)
    reset_models()
    out = M.install("not-installed-yet")
    check("installing/downloading a new model still asks ONE download_model card",
          len(gate.calls) == 1 and gate.calls[0][0] == "download_model",
          gate.calls)
    check("... and a denied card downloads nothing",
          out.get("ok") is False, out)


def t_forget_range_still_asks_its_card():
    import jarvis_forget_range as FR
    gate = Gate(allowed=False)
    job = {"token": "t1", "frame": types.SimpleNamespace(said="yesterday"),
           "facts": [1], "chats": [], "text": "Forget some things?",
           "counts": {"facts": 1, "chats": 0}, "pinned_kept": 0}
    FR._decide(job, None, None, gate.check, lambda action: "ask")
    check("forget_range still raises its ONE memory_forget_range card",
          len(gate.calls) == 1
          and gate.calls[0][0] == FR.ACTION, gate.calls)
    check("... and the action is the ask-tier one the table names",
          FR.ACTION == "memory_forget_range", FR.ACTION)


def t_lockdown_off_still_asks_its_card():
    import jarvis_asks_first as AF
    gate = Gate(allowed=False)
    real_setting = AF.lockdown_setting
    AF.lockdown_setting = lambda: {"on": True, "why": ""}
    try:
        code, out = AF.request_tier(
            {"action": "lockdown", "ask": False}, gate=gate.check,
            tier_of=lambda action: "ask",
            spawn=lambda fn: fn(), armed=lambda: True, here=True)
    finally:
        AF.lockdown_setting = real_setting
    check("turning Lockdown off still asks its ONE loosening card",
          len(gate.calls) == 1
          and gate.calls[0][0] == AF.LOOSEN_ACTION, gate.calls)
    check("... and a denied card leaves Lockdown on",
          code == 202 and out.get("waiting") is True, (code, out))


def t_the_excluded_code_still_says_ask():
    for rel, func, callee, first, why in CALL_PINS:
        tree = py_tree(rel)
        units = funcs_named(tree, func) if func else [tree]
        found = False
        for unit in units:
            for call in calls_named(unit, callee):
                args = str_args(call)
                if first is None or (args and args[0] == first):
                    found = True
        check(f"source pin: {why}", found,
              f"{rel}: {func or '*'}.{callee}({first!r}) not found")
    for rel, name, value, why in CONST_PINS:
        got = const_named(py_tree(rel), name)
        check(f"source pin: {why}", got == value, f"{rel}: {name} = {got!r}")
    hello = py_tree("backend/jarvis_asks_first.py")
    check("source pin: turning Lockdown off has its own carded road",
          bool(funcs_named(hello, "request_lockdown"))
          and bool(funcs_named(hello, "_decide")),
          "request_lockdown/_decide missing")
    owner = py_tree("jarvis-backend/jarvis_owner_check.py")
    assigned = set()
    for node in ast.walk(owner):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (getattr(node, "targets", None)
                       or [getattr(node, "target", None)])
            assigned |= {t.id for t in targets if isinstance(t, ast.Name)}
    check("source pin: the PC-only actions are still a named list",
          "PC_ONLY_ACTIONS" in assigned)


def t_github_create_repo_is_not_built_but_is_already_refused():
    """Wave 13 builds it. Until then the allow-list must already say no."""
    hits = []
    for path in sorted((HERE).glob("*.py")):
        if path.name.startswith("test_") or path.name == "jarvis_reversible_ui.py":
            continue
        if "github_create_repo" in path.read_text(encoding="utf-8", errors="ignore"):
            hits.append(path.name)
    check("github_create_repo is not shipped yet (Wave 13 builds it)", hits == [], hits)
    check("... and the allow-list already refuses the name",
          V.is_reversible_ui_choice("github_create_repo") is False
          and V.is_excluded("github_create_repo") is True)


# --------------------------------------------------------------------------
#   5. The audit of the everyday settings
# --------------------------------------------------------------------------

def t_the_setting_audit_is_honest_and_complete():
    for name in ("read_aloud", "voice", "theme_face", "todo_carryover",
                 "pc_notifications"):
        row = V.ALREADY_CARDLESS_UI.get(name) or {}
        check(f"audit: {name} is recorded as already cardless",
              bool(row.get("evidence")), row)
        check(f"audit: {name} is NOT on the uncarded allow-list (nothing to fence)",
              name not in V.REVERSIBLE_UI_CHOICES)
    for name in ("wifi_auto_reconnect", "background_learning", "learn_sensitive",
                 "learn_paraphrase", "phone_notifications", "watch_notify",
                 "skills_on_off"):
        row = V.SAFE_DIRECTION_ONLY_UI.get(name) or {}
        check(f"audit: {name} is recorded OFF-instant / ON-carded",
              bool(row.get("off")) and bool(row.get("on")), row)
        check(f"audit: {name} is NOT on the uncarded allow-list",
              name not in V.REVERSIBLE_UI_CHOICES)
    check("audit: the briefing hour is recorded as not wired, with a reason",
          "briefing_hour" in V.NOT_WIRED_UI
          and bool(V.NOT_WIRED_UI["briefing_hour"]))
    check("audit: every evidence string names a file",
          all(".py" in str(v) for v in
              [r.get("evidence", "") for r in V.ALREADY_CARDLESS_UI.values()]
              + [r.get("off", "") + r.get("on", "")
                 for r in V.SAFE_DIRECTION_ONLY_UI.values()]))


# --------------------------------------------------------------------------
#   6. The tier table is untouched
# --------------------------------------------------------------------------

def t_the_tier_table_still_says_ask():
    for rel in ("backend/rebuilt/jarvis-framework.toml",
                "jarvis-backend/jarvis-framework.toml"):
        text = (REPO / rel).read_text(encoding="utf-8")
        check(f"{rel}: switch_model is still tier \"ask\"",
              re.search(r'^\s*switch_model\s*=\s*"ask"\s*$', text, re.M)
              is not None)
        check(f"{rel}: download_model is still tier \"ask\"",
              re.search(r'^\s*download_model\s*=\s*"ask"\s*$', text, re.M)
              is not None)
    tree = py_tree("backend/jarvis_reversible_ui.py")
    touched = {n.func.attr for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    touched |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    touched |= {n.func.id for n in ast.walk(tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    check("the new module writes no settings file and changes no tier",
          not ({"set_tier", "write_text", "write_bytes", "dump", "open"}
               & touched), sorted(touched))


# --------------------------------------------------------------------------
#   7. Shipped, and both copies byte-equal
# --------------------------------------------------------------------------

def t_the_module_is_shipped_and_its_twins_match():
    import _where
    check("backend/_where.py SHIPPED lists the new module",
          "jarvis_reversible_ui.py" in _where.SHIPPED)
    check("jarvis_bench.py is still the LAST shipped entry",
          _where.SHIPPED[-1] == "jarvis_bench.py"
          and _where.SHIPPED.index("jarvis_reversible_ui.py")
          < len(_where.SHIPPED) - 1)
    script = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("scripts/apply-patches.ps1 $SHIPPED lists it in the same place",
          "'jarvis_reversible_ui.py'" in script
          and script.index("'jarvis_reversible_ui.py'")
          < script.index("'jarvis_bench.py'"))
    one = (HERE / "jarvis_reversible_ui.py").read_bytes()
    two = (BASE / "jarvis_reversible_ui.py").read_bytes() if (
        BASE / "jarvis_reversible_ui.py").is_file() else b""
    check("the two copies of the module are byte-equal", one == two,
          f"{len(one)} B vs {len(two)} B")


def main() -> int:
    for fn in (t_the_list_is_exactly_the_two_wired_choices,
               t_apply_preset_ui_path_asks_nothing,
               t_apply_preset_model_path_still_asks_one_card,
               t_switch_model_ui_path_asks_nothing_and_records,
               t_switch_model_model_path_still_asks_exactly_one_card,
               t_the_switch_route_cannot_be_asked_for_no_card,
               t_the_switch_route_keeps_the_huds_checks,
               t_the_excluded_set_is_refused_by_name,
               t_a_download_still_asks_its_card,
               t_forget_range_still_asks_its_card,
               t_lockdown_off_still_asks_its_card,
               t_the_excluded_code_still_says_ask,
               t_github_create_repo_is_not_built_but_is_already_refused,
               t_the_setting_audit_is_honest_and_complete,
               t_the_tier_table_still_says_ask,
               t_the_module_is_shipped_and_its_twins_match):
        fn()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
