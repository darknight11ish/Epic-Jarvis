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
  2. jarvis_memory.quiet_onnxruntime() calls it, and both fastembed load
     sites (the meaning model and the re-ranker) call quiet_onnxruntime()
     before they import fastembed.
  3. A missing onnxruntime, or one whose switch raises, is harmless - and a
     switch that raises does NOT leave the module without onnxruntime.
  4. With the real onnxruntime installed (the owner's PC), the call works.
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


def t_both_fastembed_sites_call_it_first():
    """Read the source: in every function that imports fastembed, the call
    to quiet_onnxruntime() comes before the import."""
    tree = ast.parse((HERE / "rebuilt" / "jarvis_memory.py").read_text(encoding="utf-8"))
    sites = 0
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        imports = [n for n in ast.walk(fn) if isinstance(n, ast.ImportFrom)
                   and (n.module or "").startswith("fastembed")]
        if not imports:
            continue
        sites += 1
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                 and getattr(n.func, "id", "") == "quiet_onnxruntime"]
        first_import = min(n.lineno for n in imports)
        check(f"{fn.name}: quiet_onnxruntime() before fastembed",
              any(c.lineno < first_import for c in calls))
    check("both fastembed load sites were found", sites == 2, f"found {sites}")


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
               t_both_fastembed_sites_call_it_first, t_real_onnxruntime):
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
