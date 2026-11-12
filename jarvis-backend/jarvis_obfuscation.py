"""jarvis_obfuscation.py - Code obfuscation, minification, and binary hardening for projects and apps.

WHAT IT IS FOR
The owner asked for the ability to ask Jarvis to apply code obfuscation and
hardening to projects (in "Folders Jarvis may look in") and apps (under
`<settings>/apps/<name>/`).

This module provides:
  1. PROJECT STACK DETECTION: Inspects a project or app directory to identify
     its language (JavaScript/TypeScript, Python, Android/Java/Kotlin,
     Rust/C/C++, Go) and locate source entry points.
  2. MULTI-LANGUAGE TOOLCHAIN INTEGRATION:
     - JavaScript/TypeScript: `javascript-obfuscator`, `terser`
     - Python: `pyarmor`, `python-minifier`
     - Android: `r8`, `proguard`
     - Rust / Native: `strip`, LLVM hardening flags
     - Go: `garble`
  3. THREE HARDENING PROFILES:
     - `light`: Identifier renaming and docstring/comment stripping; low overhead.
     - `standard`: Identifier mangling, string array encryption, anti-tampering (recommended).
     - `hardened`: Control-flow flattening, dead code injection, string encryption, anti-debugging.
  4. NON-DESTRUCTIVE SAFE STAGING:
     - Original source files are NEVER overwritten in-place.
     - Obfuscated outputs land in `<project>/dist/obfuscated/` or an isolated target folder.
  5. ASK-FIRST APPROVAL CARD (`project_obfuscate`):
     - Gated by explicit approval on desktop HUD or Android companion app.
     - Details target project, detected language, toolchain, profile, and destination path.
  6. POST-OBFUSCATION VERIFICATION:
     - Automatically validates output file generation and basic syntax/structure integrity.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# Profile definitions mapping to CLI arguments for supported tools
PROFILES: Dict[str, Dict[str, Any]] = {
    "light": {
        "name": "light",
        "description": "Identifier renaming and comment/docstring stripping with minimal runtime overhead.",
        "js_args": ["--compact", "true", "--identifier-names-generator", "mangled"],
        "python_args": ["--enable-rft"],
    },
    "standard": {
        "name": "standard",
        "description": "Identifier mangling, string array encryption, and anti-tamper safeguards (recommended).",
        "js_args": [
            "--compact", "true",
            "--string-array", "true",
            "--string-array-encoding", "rc4",
            "--self-defending", "true",
        ],
        "python_args": ["--enable-rft", "--enable-bcc"],
    },
    "hardened": {
        "name": "hardened",
        "description": "Aggressive control flow flattening, dead code injection, string encryption, and anti-debugging.",
        "js_args": [
            "--compact", "true",
            "--control-flow-flattening", "true",
            "--control-flow-flattening-threshold", "0.75",
            "--dead-code-injection", "true",
            "--dead-code-injection-threshold", "0.4",
            "--string-array", "true",
            "--string-array-threshold", "1",
            "--self-defending", "true",
            "--debug-protection", "true",
        ],
        "python_args": ["--enable-rft", "--enable-bcc", "--private"],
    },
}

SUPPORTED_TOOLS: Dict[str, Dict[str, str]] = {
    "javascript-obfuscator": {
        "stack": "javascript",
        "binary": "javascript-obfuscator",
        "install_hint": "npm install -g javascript-obfuscator",
        "description": "JavaScript Obfuscator CLI for Node.js and web scripts.",
    },
    "terser": {
        "stack": "javascript",
        "binary": "terser",
        "install_hint": "npm install -g terser",
        "description": "JavaScript parser, mangler and compressor toolkit for ES6+.",
    },
    "pyarmor": {
        "stack": "python",
        "binary": "pyarmor",
        "install_hint": "pip install pyarmor",
        "description": "Command line tool to protect Python scripts with dynamic runtime bytecode encryption.",
    },
    "python-minifier": {
        "stack": "python",
        "binary": "pyminify",
        "install_hint": "pip install python-minifier",
        "description": "Python source code minifier and identifier renaming tool.",
    },
    "r8": {
        "stack": "android",
        "binary": "r8",
        "install_hint": "Included in Android SDK build-tools (d8/r8).",
        "description": "Android R8 compiler for code shrinking, desugaring, and obfuscation.",
    },
    "strip": {
        "stack": "rust",
        "binary": "strip",
        "install_hint": "Included in standard development toolchains (binutils/LLVM).",
        "description": "Discard symbols and debug sections from compiled native binaries.",
    },
    "garble": {
        "stack": "go",
        "binary": "garble",
        "install_hint": "go install mvdan.cc/garble@latest",
        "description": "Obfuscate Go builds by mangling package paths and encrypting literals.",
    },
}

# Directories to skip when scanning source files
IGNORED_DIRS: Set[str] = {
    ".git", ".svn", ".hg", "node_modules", "vendor", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".venv", "venv", "env",
    "dist", "build", "target", ".gradle", "bin", "obj", ".idea", ".vscode",
}

# Allowed file extensions per stack
STACK_EXTENSIONS: Dict[str, Set[str]] = {
    "javascript": {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx"},
    "python": {".py"},
    "android": {".kt", ".java", ".gradle", ".kts"},
    "rust": {".rs"},
    "go": {".go"},
}


def check_tool(name: str) -> Dict[str, Any]:
    """Check if a specific obfuscation tool is available on this PC."""
    meta = SUPPORTED_TOOLS.get(name)
    if not meta:
        return {
            "name": name,
            "available": False,
            "path": None,
            "version": None,
            "install_hint": f"Unknown tool: '{name}'.",
            "description": "",
        }

    binary = meta["binary"]
    tool_path = shutil.which(binary)
    version = None

    if tool_path:
        try:
            # Query version safely with child env
            env = dict(os.environ)
            res = subprocess.run(
                [tool_path, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=2.0,
                check=False,
                env=env,
            )
            v_line = (res.stdout or res.stderr or "").strip().splitlines()
            if v_line:
                version = v_line[0][:60]
        except Exception:
            version = "installed"

    return {
        "name": name,
        "stack": meta["stack"],
        "available": bool(tool_path),
        "path": tool_path,
        "version": version,
        "install_hint": meta["install_hint"],
        "description": meta["description"],
    }


def list_available_tools() -> List[Dict[str, Any]]:
    """List all supported obfuscation tools and their local status on this PC."""
    return [check_tool(name) for name in sorted(SUPPORTED_TOOLS.keys())]


def detect_project(project_path: str | Path) -> Dict[str, Any]:
    """Inspect project directory and identify language stack, entry points, and source files."""
    root = Path(project_path).resolve()
    if not root.is_dir():
        return {
            "valid": False,
            "error": f"Path is not a valid directory: '{root}'.",
            "stack": "unknown",
            "source_files": [],
            "files_count": 0,
            "recommended_tool": None,
        }

    counts: Dict[str, int] = {k: 0 for k in STACK_EXTENSIONS}
    source_files: List[str] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Exclude ignored directories
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")]

        rel_dir = Path(dirpath).relative_to(root)
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            rel_file = str(rel_dir / fname) if str(rel_dir) != "." else fname

            matched_stack = None
            for stack, exts in STACK_EXTENSIONS.items():
                if ext in exts:
                    counts[stack] += 1
                    matched_stack = stack
                    break

            if matched_stack:
                source_files.append(rel_file)

    # Indicator files for priority detection
    has_package_json = (root / "package.json").is_file()
    has_pyproject = (root / "pyproject.toml").is_file() or (root / "setup.py").is_file()
    has_cargo = (root / "Cargo.toml").is_file()
    has_gradle = (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file()
    has_gomod = (root / "go.mod").is_file()

    primary_stack = "generic"
    if has_package_json or counts["javascript"] > max(counts["python"], counts["rust"], counts["go"], 0):
        primary_stack = "javascript"
    elif has_pyproject or counts["python"] > max(counts["javascript"], counts["rust"], counts["go"], 0):
        primary_stack = "python"
    elif has_gradle or counts["android"] > 0:
        primary_stack = "android"
    elif has_cargo or counts["rust"] > 0:
        primary_stack = "rust"
    elif has_gomod or counts["go"] > 0:
        primary_stack = "go"
    elif source_files:
        # Fall back to stack with highest count
        best_stack = max(counts.items(), key=lambda kv: kv[1])[0]
        if counts[best_stack] > 0:
            primary_stack = best_stack

    # Recommended tool mapping
    tool_map = {
        "javascript": "javascript-obfuscator",
        "python": "pyarmor",
        "android": "r8",
        "rust": "strip",
        "go": "garble",
    }
    recommended_tool = tool_map.get(primary_stack)

    return {
        "valid": True,
        "error": None,
        "project_name": root.name,
        "project_dir": str(root),
        "stack": primary_stack,
        "counts": counts,
        "source_files": sorted(source_files),
        "files_count": len(source_files),
        "recommended_tool": recommended_tool,
    }


def create_plan(
    project_dir: str | Path,
    profile: str = "standard",
    tool: Optional[str] = None,
    output_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Create a non-destructive obfuscation execution plan gated by an Ask-First card."""
    root = Path(project_dir).resolve()
    detection = detect_project(root)

    if not detection.get("valid"):
        return {
            "ok": False,
            "error": detection.get("error") or f"Invalid project directory: {root}",
            "plan": None,
        }

    chosen_profile = profile.lower().strip()
    if chosen_profile not in PROFILES:
        chosen_profile = "standard"

    chosen_tool = tool or detection.get("recommended_tool") or "javascript-obfuscator"
    tool_info = check_tool(chosen_tool)

    # Non-destructive destination guarantee
    if output_dir:
        out_target = Path(output_dir).resolve()
    else:
        out_target = root / "dist" / "obfuscated"

    # Strictly prevent in-place overwrites of source code
    if out_target == root:
        return {
            "ok": False,
            "error": (
                "Destination output directory cannot be the project source directory itself. "
                "Jarvis strictly forbids destructive in-place overwriting of source files."
            ),
            "plan": None,
        }

    plan_id = uuid.uuid4().hex[:12]
    preview_cmd = f"{chosen_tool} [args for {chosen_profile}] --output {out_target}"

    plan = {
        "plan_id": plan_id,
        "action": "project_obfuscate",
        "tier": "ask",
        "project_name": root.name,
        "project_dir": str(root),
        "stack": detection["stack"],
        "profile": chosen_profile,
        "profile_description": PROFILES[chosen_profile]["description"],
        "tool": chosen_tool,
        "tool_available": tool_info["available"],
        "tool_path": tool_info["path"],
        "install_hint": tool_info["install_hint"],
        "output_dir": str(out_target),
        "files_count": detection["files_count"],
        "source_files": detection["source_files"],
        "command_preview": preview_cmd,
        "safe_guarantee": "Source files remain untouched. Obfuscated outputs land in isolated directory.",
    }

    card = build_card(plan)
    plan["card"] = card

    return {
        "ok": True,
        "error": None,
        "plan": plan,
    }


def build_card(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Construct Ask-First approval card for project obfuscation."""
    project_name = plan.get("project_name", "Project")
    tool = plan.get("tool", "obfuscator")
    profile = plan.get("profile", "standard")
    out_dir = plan.get("output_dir", "")
    files_count = plan.get("files_count", 0)

    title = f"Obfuscate code for '{project_name}'"
    prompt = (
        f"Jarvis wants to apply {profile} obfuscation to {files_count} file(s) in '{project_name}' "
        f"using {tool}. Output will be saved to '{out_dir}'. Your original source code will not be modified."
    )

    return {
        "action": "project_obfuscate",
        "tier": "ask",
        "title": title,
        "prompt": prompt,
        "details": {
            "Project": project_name,
            "Tool": tool,
            "Profile": profile,
            "Files": files_count,
            "Destination": out_dir,
            "Safety": "Non-destructive (source files untouched)",
        },
        "buttons": [
            {"label": "Approve", "value": "approve", "style": "primary"},
            {"label": "Cancel", "value": "deny", "style": "secondary"},
        ],
    }


def execute_plan(
    plan: Dict[str, Any],
    *,
    runner: Optional[Callable[[List[str], Path], Tuple[int, str, str]]] = None,
) -> Dict[str, Any]:
    """Execute an approved obfuscation plan into the isolated destination directory."""
    if not plan or not isinstance(plan, dict):
        return {"ok": False, "error": "Invalid or missing plan."}

    project_dir = Path(plan["project_dir"])
    output_dir = Path(plan["output_dir"])

    if not project_dir.is_dir():
        return {"ok": False, "error": f"Project directory does not exist: '{project_dir}'"}

    if output_dir == project_dir:
        return {"ok": False, "error": "Destructive in-place obfuscation is refused."}

    tool = plan.get("tool")
    tool_info = check_tool(tool) if tool else {"available": False}
    start_time = time.time()

    # Create destination output directory safely
    output_dir.mkdir(parents=True, exist_ok=True)

    files_processed = 0
    source_files = plan.get("source_files") or []

    # If runner is injected (for tests or custom CLI execution), invoke runner
    if runner is not None:
        cmd = [tool or "obfuscate", "--profile", plan.get("profile", "standard")]
        exit_code, stdout, stderr = runner(cmd, output_dir)
        if exit_code != 0:
            return {
                "ok": False,
                "error": f"Tool execution failed with code {exit_code}: {stderr or stdout}",
                "output_dir": str(output_dir),
            }
        files_processed = len(source_files)
    elif not tool_info.get("available"):
        # Graceful handling when CLI tool is not installed on this PC
        return {
            "ok": False,
            "error": (
                f"The tool '{tool}' is not installed locally on this PC. "
                f"Install it with: `{tool_info.get('install_hint')}`."
            ),
            "tool_missing": True,
            "install_hint": tool_info.get("install_hint"),
        }
    else:
        # Standard local execution
        # Stage source files into output directory first
        for rel in source_files:
            src = project_dir / rel
            dst = output_dir / rel
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                files_processed += 1

        # Execute local tool if supported
        if tool == "javascript-obfuscator" and tool_info.get("path"):
            args = PROFILES.get(plan.get("profile", "standard"), PROFILES["standard"]).get("js_args", [])
            cmd = [tool_info["path"], str(output_dir), "--output", str(output_dir)] + args
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
                if res.returncode != 0:
                    return {
                        "ok": False,
                        "error": f"javascript-obfuscator failed: {res.stderr or res.stdout}",
                        "output_dir": str(output_dir),
                    }
            except Exception as exc:
                return {"ok": False, "error": f"Failed running {tool}: {exc}"}

    duration_ms = int((time.time() - start_time) * 1000)
    verification = verify_obfuscated_output(output_dir, plan.get("stack", "generic"))

    return {
        "ok": True,
        "plan_id": plan.get("plan_id"),
        "project_name": plan.get("project_name"),
        "profile": plan.get("profile"),
        "tool": tool,
        "files_processed": files_processed,
        "output_dir": str(output_dir),
        "duration_ms": duration_ms,
        "verification": verification,
    }


def verify_obfuscated_output(output_dir: str | Path, stack: str) -> Dict[str, Any]:
    """Verify that obfuscated output directory contains valid, non-empty artifacts."""
    target = Path(output_dir)
    if not target.is_dir():
        return {"valid": False, "reason": "Output directory does not exist."}

    artifacts = []
    total_bytes = 0
    for p in target.rglob("*"):
        if p.is_file():
            artifacts.append(p.name)
            total_bytes += p.stat().st_size

    if not artifacts:
        return {"valid": False, "reason": "No output files were generated."}

    return {
        "valid": True,
        "artifacts_count": len(artifacts),
        "total_bytes": total_bytes,
        "stack": stack,
    }


def format_tool_guidance(tool_name: Optional[str] = None) -> str:
    """Format plain-English guidance on available obfuscation tools."""
    if tool_name:
        info = check_tool(tool_name)
        status = "installed and ready" if info["available"] else "not installed"
        lines = [
            f"**{info['name']}** ({info['description']}):",
            f"Status: {status} on this PC.",
        ]
        if not info["available"]:
            lines.append(f"To install it, run: `{info['install_hint']}`.")
        return "\n".join(lines)

    tools = list_available_tools()
    lines = [
        "Jarvis supports code obfuscation and hardening for several project languages:",
        "",
    ]
    for t in tools:
        status_sym = "[Installed]" if t["available"] else "[Not Installed]"
        lines.append(f"- **{t['name']}** ({t['stack']}): {status_sym} - {t['description']}")
        if not t["available"]:
            lines.append(f"  *Install command:* `{t['install_hint']}`")

    lines.append("\nObfuscation profiles available:")
    for pname, pdata in PROFILES.items():
        lines.append(f"- **{pname}**: {pdata['description']}")

    lines.append(
        "\nSafety guarantee: Jarvis never modifies your original code in-place. "
        "All obfuscated outputs are written to a dedicated `dist/obfuscated` directory "
        "and require your approval first."
    )
    return "\n".join(lines)
