"""ONNX Runtime's own trace events are switched off wherever Jarvis loads it.

    python3 test_ort_quiet.py

ONNX Runtime's docs/Privacy.md: trace events are ON by default in
Microsoft's builds, and on Windows they can reach Microsoft with the owner's
diagnostic-data consent. Rule 1 says nothing about the owner leaves the PC,
so every place the backend loads onnxruntime itself switches them off first
(research audit 2026-09-28, section 1.3). No network, no models. What it
proves:
  1. jarvis_wakeword and jarvis_turn call disable_telemetry_events() when
     they are imported.
  2. jarvis_memory.quiet_onnxruntime() calls it, and the two public model
     loaders - OnnxEmbedder.__init__ and OnnxReranker.__init__ - call
     quiet_onnxruntime() BEFORE _backend_for(...), the one seam that builds
     the ONNX engine (fastembed is gone; the engine is called directly,
     2026-10-21).
  3. The engine is imported in one private place only: _OnnxBackend's
     constructor (onnxruntime) and the tokenizer helper it alone calls
     (tokenizers); quiet_onnxruntime() itself is the switch, so it imports
     onnxruntime too. Nothing imports either at module level.
  4. A missing onnxruntime, or one whose switch raises, is harmless - and a
     switch that raises does NOT leave the module without onnxruntime.
  5. With the real onnxruntime installed (the owner's PC), the call works.
"""
import ast
import importlib
import sys
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

sys.path.insert(0, str(HERE / "rebuilt"))
sys.path.insert(0, str(HERE))
require_shipped("jarvis_wakeword.py", "jarvis_turn.py")

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class _FakeOrt(types.ModuleType):
    def __init__(self, raises=False):
        super().__init__("onnxruntime")
        self.calls = 0
        self.raises = raises

    def disable_telemetry_events(self):
        self.calls += 1
        if self.raises:
            raise RuntimeError("older onnxruntime")


def _fresh_import(name, fake):
    saved = sys.modules.get("onnxruntime")
    sys.modules["onnxruntime"] = fake
    sys.modules.pop(name, None)
    try:
        return importlib.import_module(name)
    finally:
        if saved is not None:
            sys.modules["onnxruntime"] = saved
        else:
            sys.modules.pop("onnxruntime", None)
        sys.modules.pop(name, None)


def t_modules_switch_it_off():
    for name in ("jarvis_wakeword", "jarvis_turn"):
        fake = _FakeOrt()
        mod = _fresh_import(name, fake)
        check(f"{name} switches trace events off on import", fake.calls == 1, f"calls={fake.calls}")
        check(f"{name} keeps onnxruntime", mod.ort is fake)


def t_a_raising_switch_is_harmless():
    for name in ("jarvis_wakeword", "jarvis_turn"):
        fake = _FakeOrt(raises=True)
        mod = _fresh_import(name, fake)
        check(f"{name}: a switch that raises is swallowed", fake.calls == 1)
        check(f"{name}: and onnxruntime is still usable", mod.ort is fake)


def t_memory_helper():
    import jarvis_memory as M
    fake = _FakeOrt()
    saved = sys.modules.get("onnxruntime")
    sys.modules["onnxruntime"] = fake
    try:
        M.quiet_onnxruntime()
        check("quiet_onnxruntime() switches trace events off", fake.calls == 1)
        fake.raises = True
        M.quiet_onnxruntime()
        check("quiet_onnxruntime() swallows a raising switch", fake.calls == 2)
        sys.modules["onnxruntime"] = None  # "import onnxruntime" now raises ImportError
        M.quiet_onnxruntime()
        check("quiet_onnxruntime() with no onnxruntime is harmless", True)
    finally:
        if saved is not None:
            sys.modules["onnxruntime"] = saved
        else:
            sys.modules.pop("onnxruntime", None)


# --------------------------------------------------------------------------
#   The new rule (2026-10-21): the engine is built behind one seam, and the
#   telemetry switch is called BEFORE that seam in both public loaders.
# --------------------------------------------------------------------------

def _enclosing(tree):
    """Every node's enclosing function, as 'Class.method' or 'function'."""
    out = {}

    def walk(node, classes, funcs):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                walk(child, classes + [child.name], funcs)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, classes, funcs + [child.name])
            else:
                label = ".".join(classes + funcs) if funcs else "(module level)"
                out[id(child)] = label
                walk(child, classes, funcs)

    walk(tree, [], [])
    return out


def _engine_imports(node):
    """The engine module names an Import/ImportFrom node brings in."""
    names = set()
    if isinstance(node, ast.Import):
        names.update(alias.name.split(".")[0] for alias in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        names.add(node.module.split(".")[0])
    return names & {"onnxruntime", "tokenizers"}


def _class_function(tree, cls, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name == name:
                    return sub
    return None


def t_the_engine_sites_are_quiet_and_one():
    """AST, because this is about WHERE calls sit: the two public loaders call
    quiet_onnxruntime() before _backend_for(), and the engine is imported in
    one private place, never at module level. No model is loaded and no engine
    is imported here - this only reads the source."""
    tree = ast.parse((HERE / "rebuilt" / "jarvis_memory.py").read_text(encoding="utf-8"))
    enclosing = _enclosing(tree)

    # 1. quiet_onnxruntime() before _backend_for(), in both public loaders.
    for cls in ("OnnxEmbedder", "OnnxReranker"):
        init = _class_function(tree, cls, "__init__")
        check(f"{cls}.__init__ exists", init is not None)
        if init is None:
            continue
        quiet = [n for n in ast.walk(init) if isinstance(n, ast.Call)
                 and getattr(n.func, "id", "") == "quiet_onnxruntime"]
        seam = [n for n in ast.walk(init) if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "_backend_for"]
        check(f"{cls}.__init__ calls both quiet_onnxruntime() and _backend_for()",
              len(quiet) == 1 and len(seam) == 1, (len(quiet), len(seam)))
        check(f"{cls}.__init__ calls quiet_onnxruntime() BEFORE _backend_for() "
              "(the engine is not opened before telemetry is off)",
              bool(quiet) and bool(seam) and quiet[0].lineno < seam[0].lineno,
              [(n.lineno, getattr(n.func, "id", "?")) for n in quiet + seam])

    # 2. The engine is imported only in the private ONNX plumbing.
    sites, at_module_level, fastembed = {}, False, []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        mods = _engine_imports(node)
        if mods:
            label = enclosing.get(id(node), "?")
            if label == "(module level)":
                at_module_level = True
            sites.setdefault(label, set()).update(mods)
        module = getattr(node, "module", None) or ""
        if module.startswith("fastembed") or any(
                alias.name.startswith("fastembed") for alias in node.names):
            fastembed.append(node.lineno)
    allowed = {"quiet_onnxruntime", "_OnnxBackend.__init__", "_load_tokenizer",
               "_download_snapshot"}
    check("the engine (onnxruntime/tokenizers) is imported only inside the "
          "private ONNX plumbing", set(sites) <= allowed, sites)
    check("... onnxruntime in the telemetry switch and the one backend",
          sites.get("quiet_onnxruntime") == {"onnxruntime"}
          and "onnxruntime" in sites.get("_OnnxBackend.__init__", set()), sites)
    check("... tokenizers only in the loader's own tokenizer helper",
          sites.get("_load_tokenizer") == {"tokenizers"}, sites)
    check("nothing imports the engine at module level", at_module_level is False, sites)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "id", "") == "_load_tokenizer"]
    check("_load_tokenizer() is only called by _OnnxBackend.__init__",
          len(calls) == 1
          and enclosing.get(id(calls[0])) == "_OnnxBackend.__init__",
          [enclosing.get(id(n)) for n in calls])
    check("no fastembed imports are left anywhere in the module", fastembed == [],
          fastembed)


def t_real_onnxruntime():
    try:
        import onnxruntime
    except Exception:
        SKIPPED.append("t_real_onnxruntime")
        print("skip  onnxruntime is not installed here")
        return
    try:
        onnxruntime.disable_telemetry_events()
        check("the real onnxruntime accepts the call", True)
    except Exception as exc:
        check("the real onnxruntime accepts the call", False, repr(exc))


if __name__ == "__main__":
    for fn in (t_modules_switch_it_off, t_a_raising_switch_is_harmless, t_memory_helper,
               t_the_engine_sites_are_quiet_and_one, t_real_onnxruntime):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        sys.exit(1)
