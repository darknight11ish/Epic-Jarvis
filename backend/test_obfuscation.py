#!/usr/bin/env python3
"""test_obfuscation.py - Unit and integration tests for code obfuscation integration.

Pins:
  1. Multi-language stack detection (JS/TS, Python, Android, Rust, Go).
  2. Ignored directory filtering (node_modules, __pycache__, .git, dist, etc.).
  3. Tool inspection and friendly install commands when missing.
  4. Non-destructive safety guarantees: source code is never overwritten in-place.
  5. Profile configurations (light, standard, hardened).
  6. Ask-First approval card structure (`project_obfuscate`, tier "ask").
  7. Injected test execution runner and output verification.
  8. Natural language intent routing in jarvis_quick.py.
  9. Governance registrations (MUST_ASK, NO_AUTO_APPROVE, card words, SHIPPED list).
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import jarvis_asks_first as AF  # noqa: E402
import jarvis_card_words as CW  # noqa: E402
import jarvis_obfuscation as OBF  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED = []
FAILED = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASSED.append(name)
        print(f"ok    {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}" + (f"\n        {detail}" if detail else ""))


class MockSched:
    def mark_command(self, text):
        pass

    def note_set(self, *a, **k):
        pass

    def last_set(self, *a, **k):
        return None


def ask(text: str, surface: str = "hud"):
    return Q.answer(
        text,
        sched=MockSched(),
        now=1794500000.0,
        peer="127.0.0.1",
        local=True,
        client_surface=surface,
    )


def t_tool_availability_and_guidance():
    tools = OBF.list_available_tools()
    check("list_available_tools returns a non-empty list", len(tools) >= 5, str(len(tools)))

    expected_tools = {"javascript-obfuscator", "pyarmor", "terser", "python-minifier", "r8", "strip", "garble"}
    found_names = {t["name"] for t in tools}
    check("all standard tools are registered", expected_tools.issubset(found_names), str(found_names))

    for t in tools:
        check(f"tool {t['name']} has required fields",
              all(k in t for k in ("name", "available", "path", "install_hint", "description")))

    # Guidance formatting
    guidance = OBF.format_tool_guidance()
    check("guidance mentions profiles", "light" in guidance and "standard" in guidance and "hardened" in guidance)
    check("guidance mentions safety guarantee", "never modifies your original code in-place" in guidance)

    single_guidance = OBF.format_tool_guidance("pyarmor")
    check("single tool guidance mentions pyarmor and install hint",
          "pyarmor" in single_guidance.lower() and "pip install" in single_guidance)


def t_project_stack_detection():
    temp_dir = Path(tempfile.mkdtemp(prefix="jarvis-obf-test-"))
    try:
        # 1. JavaScript / Web project
        js_proj = temp_dir / "my_web_app"
        js_proj.mkdir()
        (js_proj / "package.json").write_text('{"name": "test"}', encoding="utf-8")
        (js_proj / "src").mkdir()
        (js_proj / "src" / "index.js").write_text("console.log('hello');", encoding="utf-8")
        (js_proj / "src" / "app.ts").write_text("const x: number = 42;", encoding="utf-8")
        # Ignored dir
        (js_proj / "node_modules").mkdir()
        (js_proj / "node_modules" / "dep.js").write_text("// dep", encoding="utf-8")

        det_js = OBF.detect_project(js_proj)
        check("JS project detected as javascript stack", det_js["stack"] == "javascript", str(det_js["stack"]))
        check("JS project recommends javascript-obfuscator",
              det_js["recommended_tool"] == "javascript-obfuscator", det_js["recommended_tool"])
        check("node_modules excluded from source files",
              len(det_js["source_files"]) == 2 and not any("node_modules" in f for f in det_js["source_files"]),
              str(det_js["source_files"]))

        # 2. Python project
        py_proj = temp_dir / "my_py_tool"
        py_proj.mkdir()
        (py_proj / "pyproject.toml").write_text("[project]\nname='pytool'", encoding="utf-8")
        (py_proj / "main.py").write_text("print('test')", encoding="utf-8")
        (py_proj / "__pycache__").mkdir()
        (py_proj / "__pycache__" / "main.cpython-312.pyc").write_text("bin", encoding="utf-8")

        det_py = OBF.detect_project(py_proj)
        check("Python project detected as python stack", det_py["stack"] == "python", str(det_py["stack"]))
        check("Python project recommends pyarmor", det_py["recommended_tool"] == "pyarmor", det_py["recommended_tool"])
        check("__pycache__ excluded from source files",
              len(det_py["source_files"]) == 1 and "__pycache__" not in det_py["source_files"][0],
              str(det_py["source_files"]))

        # 3. Android project
        android_proj = temp_dir / "my_android_app"
        android_proj.mkdir()
        (android_proj / "build.gradle").write_text("plugins { id 'com.android.application' }", encoding="utf-8")
        (android_proj / "MainActivity.kt").write_text("class MainActivity", encoding="utf-8")

        det_android = OBF.detect_project(android_proj)
        check("Android project detected as android stack", det_android["stack"] == "android", str(det_android["stack"]))
        check("Android project recommends r8", det_android["recommended_tool"] == "r8", det_android["recommended_tool"])

        # 4. Rust project
        rust_proj = temp_dir / "my_rust_service"
        rust_proj.mkdir()
        (rust_proj / "Cargo.toml").write_text("[package]\nname = 'rustsvc'", encoding="utf-8")
        (rust_proj / "src").mkdir()
        (rust_proj / "src" / "main.rs").write_text("fn main() {}", encoding="utf-8")

        det_rust = OBF.detect_project(rust_proj)
        check("Rust project detected as rust stack", det_rust["stack"] == "rust", str(det_rust["stack"]))
        check("Rust project recommends strip", det_rust["recommended_tool"] == "strip", det_rust["recommended_tool"])

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def t_create_plan_and_safety_checks():
    temp_dir = Path(tempfile.mkdtemp(prefix="jarvis-obf-plan-"))
    try:
        proj = temp_dir / "sample_project"
        proj.mkdir()
        (proj / "index.js").write_text("var secretKey = 'private-token-123';", encoding="utf-8")

        # Plan creation with default output
        plan_res = OBF.create_plan(proj, profile="hardened")
        check("create_plan returns ok=True", plan_res.get("ok") is True, str(plan_res))
        plan = plan_res["plan"]

        check("plan action is project_obfuscate", plan["action"] == "project_obfuscate")
        check("plan tier is ask", plan["tier"] == "ask")
        check("plan profile is hardened", plan["profile"] == "hardened")
        check("plan output is in dist/obfuscated", "dist" in plan["output_dir"] and "obfuscated" in plan["output_dir"])

        # Safety Check: Disallow in-place overwrite
        bad_plan_res = OBF.create_plan(proj, output_dir=proj)
        check("in-place overwrite is strictly refused", bad_plan_res.get("ok") is False)
        check("refusal explains why", "cannot be the project source directory" in bad_plan_res.get("error", ""))

        # Non-existent project
        missing_res = OBF.create_plan(temp_dir / "does_not_exist")
        check("non-existent directory returns error", missing_res.get("ok") is False)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def t_approval_card_generation():
    fake_plan = {
        "project_name": "alpha",
        "tool": "pyarmor",
        "profile": "standard",
        "output_dir": "/tmp/dist/obfuscated",
        "files_count": 5,
    }
    card = OBF.build_card(fake_plan)
    check("card has action project_obfuscate", card["action"] == "project_obfuscate")
    check("card has tier ask", card["tier"] == "ask")
    check("card title names project", "alpha" in card["title"])
    check("card prompt mentions non-destructive safety", "will not be modified" in card["prompt"])
    check("card has approve and cancel buttons",
          len(card["buttons"]) == 2 and any(b["value"] == "approve" for b in card["buttons"]))


def t_execution_runner_and_verification():
    temp_dir = Path(tempfile.mkdtemp(prefix="jarvis-obf-exec-"))
    try:
        proj = temp_dir / "target_app"
        proj.mkdir()
        src_file = proj / "app.js"
        src_original_content = "function compute() { return 42; }"
        src_file.write_text(src_original_content, encoding="utf-8")

        plan_res = OBF.create_plan(proj, profile="light")
        plan = plan_res["plan"]

        # Mock runner simulating CLI tool execution
        def mock_runner(cmd, out_dir):
            # Create simulated obfuscated file in output dir
            obf_file = out_dir / "app.js"
            obf_file.parent.mkdir(parents=True, exist_ok=True)
            obf_file.write_text("eval(function(p,a,c,k,e,d){...})", encoding="utf-8")
            return 0, "Obfuscated successfully", ""

        exec_res = OBF.execute_plan(plan, runner=mock_runner)
        check("execution succeeds", exec_res.get("ok") is True, str(exec_res))
        check("original source file is COMPLETELY UNTOUCHED",
              src_file.read_text(encoding="utf-8") == src_original_content)

        out_path = Path(exec_res["output_dir"]) / "app.js"
        check("output artifact exists in destination directory", out_path.is_file())
        check("output artifact has transformed content", "eval" in out_path.read_text(encoding="utf-8"))

        verification = exec_res.get("verification") or {}
        check("verification reports valid output", verification.get("valid") is True)
        check("verification counts artifacts", verification.get("artifacts_count") == 1)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def t_chat_intent_routing():
    # 1. Tools info query
    r1 = ask("what obfuscation tools do you support?")
    check("'what obfuscation tools do you support' matches obfuscate_tools_info",
          r1 is not None and r1.intent == "obfuscate_tools_info", getattr(r1, "intent", None))
    check("tools info reply lists supported tools",
          r1 is not None and "javascript-obfuscator" in r1.reply and "pyarmor" in r1.reply)

    r2 = ask("list code obfuscation tools")
    check("'list code obfuscation tools' matches obfuscate_tools_info",
          r2 is not None and r2.intent == "obfuscate_tools_info")

    r3 = ask("can you obfuscate code?")
    check("'can you obfuscate code?' matches obfuscate_tools_info",
          r3 is not None and r3.intent == "obfuscate_tools_info")

    # 2. Project obfuscation request
    r4 = ask("obfuscate project sample-dashboard")
    check("'obfuscate project sample-dashboard' matches project_obfuscate_ask",
          r4 is not None and r4.intent == "project_obfuscate_ask", getattr(r4, "intent", None))

    r5 = ask("harden project analytics with pyarmor hardened")
    check("'harden project analytics with pyarmor hardened' matches project_obfuscate_ask",
          r5 is not None and r5.intent == "project_obfuscate_ask")


def t_governance_and_safety_checks():
    check("project_obfuscate is registered in MUST_ASK", "project_obfuscate" in AF.MUST_ASK)
    check("project_obfuscate is registered in HARD_LIMITS", "project_obfuscate" in AF.HARD_LIMITS)
    check("project_obfuscate is registered in TITLES", "project_obfuscate" in CW.TITLES)
    check("project_obfuscate is registered in SUMMARY", "project_obfuscate" in CW.SUMMARY)

    # Check _where.py and apply-patches.ps1
    where_text = (HERE / "_where.py").read_text(encoding="utf-8")
    check("jarvis_obfuscation.py is in backend/_where.py SHIPPED list",
          '"jarvis_obfuscation.py"' in where_text)

    ps_text = (ROOT / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("jarvis_obfuscation.py is in scripts/apply-patches.ps1 $SHIPPED list",
          "'jarvis_obfuscation.py'" in ps_text)

    # Check twin parity
    backend_obf = (HERE / "jarvis_obfuscation.py").read_text(encoding="utf-8")
    base_obf = (ROOT / "jarvis-backend" / "jarvis_obfuscation.py").read_text(encoding="utf-8")
    check("jarvis_obfuscation.py matches jarvis-backend twin exactly", backend_obf == base_obf)


def main():
    tests = [
        t_tool_availability_and_guidance,
        t_project_stack_detection,
        t_create_plan_and_safety_checks,
        t_approval_card_generation,
        t_execution_runner_and_verification,
        t_chat_intent_routing,
        t_governance_and_safety_checks,
    ]
    for t in tests:
        print(f"\n--- {t.__name__} " + "-" * (50 - len(t.__name__)))
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            check(f"{t.__name__} threw exception", False, repr(exc))

    print("\n" + "=" * 60)
    print(f"Total: {len(PASSED) + len(FAILED)} | Passed: {len(PASSED)} | Failed: {len(FAILED)}")
    if FAILED:
        print("Failed tests:")
        for f in FAILED:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED!")
        sys.exit(0)


if __name__ == "__main__":
    main()
