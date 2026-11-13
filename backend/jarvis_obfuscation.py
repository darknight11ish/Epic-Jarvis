"""jarvis_obfuscation.py - which code-protection tools this PC has, and nothing else.

WHAT THIS IS FOR
The owner asked whether Jarvis can obfuscate or harden a project. This build
cannot: there is no plan, no approval card and no execution. What is real is a
read-only inventory - which of the known code-protection tools are installed on
this PC, and which language each one belongs to.

WHAT IT DOES, IN ONE LINE EACH
  * `check_tool(name)` asks whether ONE tool is on this PC and, if so, asks that
    tool for its version. That probe is the only program this module starts.
  * `list_available_tools()` and `format_tool_guidance()` turn that into the one
    chat answer ("what obfuscation tools do you support?").

THE LIMITS, SAID HERE SO NO ANSWER OVERSTATES THEM
  * No obfuscation, minification, hardening or verification is performed.
  * No plan is built, no approval card is raised, and no project file is read,
    copied or changed. `project_obfuscate` is NOT a gate action and NOT a tool
    Jarvis offers; the chat lane says so in its own words.
  * The version probe is the only child process, and it is given
    `jarvis_child_env.inherited()` - never the backend's whole environment.
    That environment holds the pairing token (`HUD_TOKEN`, `JARVIS_TOKEN`), the
    Joplin token, the Obsidian key and every `*_KEY` / `*_PASSWORD` / `*_SECRET`
    the owner has set. CLAUDE.md rule 3: a key is sent only to the one service
    it authenticates against. `jarvis_child_env.py` says the same thing at
    length, and this is the exact leak it was written to stop.
  * If that safe environment cannot be built, the tool is NOT started at all.
    There is no fallback to the whole environment.

Standard library only, plus this repository's own `jarvis_child_env`.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Any, Dict, List, Optional

#: The tools this check knows about, and the language each one protects.
#: `binary` is the name looked up on this PC's PATH, which is not always the
#: tool's own name (`python-minifier` installs `pyminify`).
SUPPORTED_TOOLS: Dict[str, Dict[str, str]] = {
    "javascript-obfuscator": {
        "stack": "javascript",
        "binary": "javascript-obfuscator",
        "install_hint": "npm install -g javascript-obfuscator",
        "description": "JavaScript obfuscator for Node.js and web scripts.",
    },
    "terser": {
        "stack": "javascript",
        "binary": "terser",
        "install_hint": "npm install -g terser",
        "description": "JavaScript parser, mangler and compressor for ES6 and later.",
    },
    "pyarmor": {
        "stack": "python",
        "binary": "pyarmor",
        "install_hint": "pip install pyarmor",
        "description": "Protects Python scripts with encrypted runtime bytecode.",
    },
    "python-minifier": {
        "stack": "python",
        "binary": "pyminify",
        "install_hint": "pip install python-minifier",
        "description": "Minifies Python source and renames identifiers.",
    },
    "r8": {
        "stack": "android",
        "binary": "r8",
        "install_hint": "Included in the Android SDK build-tools (d8/r8).",
        "description": "Android R8 compiler for shrinking and obfuscation.",
    },
    "strip": {
        "stack": "rust",
        "binary": "strip",
        "install_hint": "Included in standard development toolchains (binutils/LLVM).",
        "description": "Removes symbols and debug sections from compiled native binaries.",
    },
    "garble": {
        "stack": "go",
        "binary": "garble",
        "install_hint": "go install mvdan.cc/garble@latest",
        "description": "Obfuscates Go builds by mangling package paths and literals.",
    },
}

#: The plain words for each language family, so an answer never prints an
#: internal key such as "javascript" at the owner.
STACK_LABELS: Dict[str, str] = {
    "javascript": "JavaScript and TypeScript",
    "python": "Python",
    "android": "Android apps (Java and Kotlin)",
    "rust": "Rust and native code",
    "go": "Go",
}

#: The one sentence every answer starts with. It is the whole honesty of this
#: module: a check, not a run.
NOT_RUN = (
    "Jarvis can check which code-protection tools are installed on this PC, but "
    "it does not run obfuscation or hardening in this build. The only program it "
    "starts is a tool's own --version, to read its version; no approval card is "
    "raised, and no files are changed."
)


def _safe_child_env() -> Optional[dict]:
    """The allowlisted environment for a child process, or None.

    None means the allowlist could not be built, and the caller must NOT start
    the program: a missing safe environment is never a reason to fall back to
    the backend's own environment. See `jarvis_child_env.py`.
    """
    try:
        import jarvis_child_env
        return jarvis_child_env.inherited()
    except Exception:                       # noqa: BLE001 - fail closed, start nothing
        return None


def check_tool(name: str) -> Dict[str, Any]:
    """Check whether ONE code-protection tool is installed on this PC.

    Returns the same fields for a known and an unknown name, so a caller can
    print the answer without a second lookup. An unknown name starts no
    program.
    """
    meta = SUPPORTED_TOOLS.get(name)
    if not meta:
        return {
            "name": str(name),
            "stack": "",
            "stack_label": "",
            "available": False,
            "path": None,
            "version": None,
            "install_hint": "",
            "description": "",
        }

    binary = meta["binary"]
    tool_path = shutil.which(binary)
    version = None

    if tool_path:
        env = _safe_child_env()
        if env is not None:
            try:
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
            except Exception:               # noqa: BLE001 - installed is still a fact
                version = None

    stack = meta["stack"]
    return {
        "name": name,
        "stack": stack,
        "stack_label": STACK_LABELS.get(stack, stack),
        "available": bool(tool_path),
        "path": tool_path,
        "version": version,
        "install_hint": meta["install_hint"],
        "description": meta["description"],
    }


def list_available_tools() -> List[Dict[str, Any]]:
    """Every tool this check knows about, with its real status on this PC."""
    return [check_tool(name) for name in sorted(SUPPORTED_TOOLS)]


def format_tool_guidance(tool_name: Optional[str] = None) -> str:
    """The honest chat answer: what is installed, and what Jarvis cannot do.

    Plain words only. It never promises a card, a plan or a run, and it never
    lists a language as handled - only as covered by the installed check.
    """
    if tool_name:
        info = check_tool(str(tool_name).strip()[:40])
        if not info["stack"]:
            return (
                f"Jarvis does not know a code-protection tool called "
                f"'{info['name']}'. Nothing was run."
            )
        status = "installed" if info["available"] else "not installed"
        lines = [
            f"**{info['name']}** ({info['stack_label']}): {status} on this PC.",
            info["description"],
        ]
        if info["available"]:
            lines.append(
                "Jarvis starts it once with its own --version to read the version "
                "above; it cannot obfuscate or harden code with it in this build."
            )
        else:
            lines.append(
                f"To install it yourself, run: `{info['install_hint']}`. Jarvis "
                "does not install it, and does not run obfuscation or hardening "
                "with it in this build."
            )
        return " ".join(lines)

    tools = list_available_tools()
    lines = [NOT_RUN, "", "Tools this check looks for:"]
    for t in tools:
        status = "Installed" if t["available"] else "Not installed"
        lines.append(f"- **{t['name']}** ({t['stack_label']}): {status}.")
        if not t["available"]:
            lines.append(f"  To install it yourself: `{t['install_hint']}`")

    languages = ", ".join(
        STACK_LABELS[k] for k in ("javascript", "python", "android", "rust", "go")
    )
    lines.append("")
    lines.append(
        f"Languages this check covers: {languages}. Jarvis cannot obfuscate or "
        "harden any of them in this build."
    )
    return "\n".join(lines)
