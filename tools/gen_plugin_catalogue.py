#!/usr/bin/env python3
"""Generate the plug-and-play catalogue from Jarvis's own patch stack.

WHAT THIS IS FOR

Every optional Jarvis feature today arrives as two things: a module copied
beside `jarvis_hud.py`, and a patch that adds ONE line to `jarvis_hud.py`
calling that module's own `install()`. That one line is the only reason a
feature cannot simply be dropped in.

This reads `scripts/apply-patches.ps1`'s own `$PATCHES` list (through
`backend/_stack.py`, the same way the test suites do), works out which
patches do nothing but that one call, and writes:

    plugins/registry.json          every patch, its bucket, and why
    plugins/ready/<name>/plugin.json   one folder per drop-in module
    plugins/ready/<name>/README.md     what it does, in plain words
    plugins/README.md              the index, generated

A patch that only makes that call needs no core change once
`plugins/loader/jarvis_plugins.py` is installed: the loader makes the call
itself, for every module in its folder.

Everything else - a patch that edits real code, or adds routes and gate
tables inline - is left in the CORE bucket, untouched and still applied by
`scripts/apply-patches.ps1` exactly as before.

Run:  py -3 tools/gen_plugin_catalogue.py [--check]
      --check fails instead of writing, the way the other gen_* tools do.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PLUGINS = ROOT / "plugins"
sys.path.insert(0, str(BACKEND))

import _stack  # noqa: E402  (path set above)

#: Modules that must never become optional. Each is a safety control, not a
#: feature: leaving one out would weaken an approval rather than remove a
#: convenience. Their patches are CORE however they are shaped. The loader's
#: own patch is here too - it is the thing that makes other patches
#: unnecessary, so it can never be one itself.
ALWAYS_CORE = {
    "owner-check.patch": "the approval gap: without it every approval is refused",
    "log-scrub.patch": "keeps keys, passwords and the pairing token out of the log",
    "stop-all.patch": "the stop everything control",
    "plugin-loader.patch": "the loader itself: the ONE startup call that makes every "
                           "other drop-in folder possible. It is what replaces the "
                           "patches, so it can never be replaced by a folder.",
}

INSTALL_CALL = re.compile(r"^(jarvis_[a-z_0-9]+)\.install\(")
IMPORT_MOD = re.compile(r"^import (jarvis_[a-z_0-9]+)$")


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].strip()


def added_removed(patch: Path) -> tuple[list[str], list[str]]:
    added, removed = [], []
    for line in patch.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
    return added, removed


def install_block(added: list[str]) -> tuple[str | None, list[str]]:
    """(module, extras).

    `module` is set when the patch adds a `try: import X; print(X.install(...))
    except: print(...)` block. `extras` is every added statement that is NOT
    part of that block - a gate-table entry, a call in a route, a function -
    which is what decides whether the feature can be a bare drop-in.
    """
    stmts: list[str] = []
    buf = ""
    for raw in added:
        code = _strip_comment(raw)
        if not code:
            continue
        buf = (buf + " " + code).strip() if buf else code
        if buf.count("(") > buf.count(")"):
            continue  # a call spanning lines
        stmts.append(buf)
        buf = ""
    if buf:
        stmts.append(buf)

    module = None
    extras: list[str] = []
    saw_install = saw_except = False
    for s in stmts:
        if s == "try:":
            continue
        m = IMPORT_MOD.match(s)
        if m:
            module = module or m.group(1)
            continue
        if s.startswith("print(") and ".install(" in s:
            inner = s[len("print("):].rstrip(")")
            m = INSTALL_CALL.match(inner)
            if not m:
                extras.append(s)
                continue
            module = module or m.group(1)
            saw_install = True
            continue
        if s.startswith("except "):
            saw_except = True
            continue
        if s == "pass":
            continue
        if s.startswith("print("):
            continue
        extras.append(s)

    if not (saw_install and saw_except):
        return None, extras
    return module, extras


def reason_for(extras: list[str]) -> str:
    """A plain-words reason a patch cannot be a bare drop-in."""
    if not extras:
        return ""
    gate = [e for e in extras if re.match(r'^"[a-z_0-9]+"\s*:', e)]
    calls = [e for e in extras if ".install(" not in e and not e.startswith('"')]
    if gate and not calls:
        return (f"also adds {len(gate)} entry/entries to the approval gate's own "
                f"tables, which decide whether the action needs a card")
    if calls and not gate:
        return (f"also changes {len(calls)} line(s) of the core's own code, "
                f"beyond calling the module")
    if calls and gate:
        return (f"also adds {len(gate)} gate entry/entries and changes "
                f"{len(calls)} line(s) of the core's own code")
    return f"adds {len(extras)} line(s) beyond the startup call"


def install_arity(module: str) -> str:
    """'handler' when the module's install() takes the core's Handler,
    'none' when it takes nothing (its own scheduler or registry hook)."""
    path = BACKEND / f"{module}.py"
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "install":
            return "handler" if node.args.args else "none"
    return "handler"


def summary_of(module: str) -> str:
    """The first sentence of the module's own header comment, tidied."""
    path = BACKEND / f"{module}.py"
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r'\s*(?:#[^\n]*\n)*\s*[rubfRUBF]{0,2}"""([\s\S]*?)"""', text)
    if not m:
        return ""
    first: list[str] = []
    for line in m.group(1).strip().splitlines():
        line = line.strip()
        if not line:
            break
        first.append(line)
    text = " ".join(first)
    text = re.sub(rf"^{re.escape(module)}\.py\s*[-:]?\s*", "", text)
    text = re.sub(r"[\u2014\u2013]", "-", text)
    text = re.sub(r"\s*\(([^()]*(?:JARVIS-API|the owner|docs/|\.md|\.patch|20\d\d)[^()]*)\)", "", text)
    text = re.sub(r"\s+-\s+.*$", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" -;,")
    if text and not text.endswith((".", "?", "!")):
        text += "."
    return text[:200]


def build() -> dict:
    order = _stack.order()
    registry: list[dict] = []
    for index, name in enumerate(order):
        path = BACKEND / name
        if not path.is_file():
            registry.append({"patch": name, "bucket": "missing", "order": index,
                             "why": "the patch file named in $PATCHES is not here"})
            continue
        added, removed = added_removed(path)
        real_removed = [l for l in removed if _strip_comment(l)]
        stem = Path(name).name[:-len(".patch")]

        if name in ALWAYS_CORE:
            registry.append({"patch": name, "bucket": "core", "order": index,
                             "why": ALWAYS_CORE[name]})
            continue

        if not real_removed:
            module, extras = install_block(added)
            if module and not extras and (BACKEND / f"{module}.py").is_file():
                registry.append({
                    "name": stem,
                    "patch": name,
                    "bucket": "plug-in",
                    "order": index,
                    "module": module,
                    "install": install_arity(module),
                    "summary": summary_of(module),
                    "why": f"adds one startup call to {module}.install(); nothing else",
                })
                continue
            if module:
                registry.append({
                    "patch": name, "bucket": "core", "order": index,
                    "module": module,
                    "why": reason_for(extras) or "adds lines to the core beyond the startup call",
                })
                continue
            registry.append({
                "patch": name, "bucket": "core", "order": index,
                "why": "adds lines to the core (routes, gate tables or a function) but removes none",
            })
            continue

        registry.append({
            "patch": name, "bucket": "core", "order": index,
            "why": "edits lines the core already has; it cannot be applied out of order",
        })

    plug_ins = [r for r in registry if r["bucket"] == "plug-in"]
    return {
        "about": (
            "Generated by tools/gen_plugin_catalogue.py from $PATCHES in "
            "scripts/apply-patches.ps1. Do not edit by hand; re-run the tool."
        ),
        "stack": "scripts/apply-patches.ps1",
        "patch_count": len(order),
        "counts": {
            "plug-in": len(plug_ins),
            "core": len([r for r in registry if r["bucket"] == "core"]),
            "missing": len([r for r in registry if r["bucket"] == "missing"]),
        },
        "entries": registry,
    }


def write_plugin_folders(data: dict) -> list[Path]:
    written: list[Path] = []
    ready = PLUGINS / "ready"
    keep = {e["name"] for e in data["entries"] if e["bucket"] == "plug-in"}

    # Prune first. A folder stays only while its feature is still a drop-in:
    # when a patch stops being one, its folder must go, or the tree keeps a
    # manifest for something that is no longer true.
    removed: list[str] = []
    if ready.is_dir():
        for child in sorted(ready.iterdir()):
            if child.is_dir() and child.name not in keep:
                shutil.rmtree(child, ignore_errors=True)
                removed.append(child.name)
    for name in removed:
        print(f"  pruned ready/{name} (no longer a drop-in module)")

    for entry in data["entries"]:
        if entry["bucket"] != "plug-in":
            continue
        folder = ready / entry["name"]
        folder.mkdir(parents=True, exist_ok=True)
        manifest = {
            "name": entry["name"],
            "summary": entry["summary"],
            "module": entry["module"],
            "install": entry["install"],
            "replaces_patch": entry["patch"],
            "stack_order": entry["order"],
        }
        p = folder / "plugin.json"
        p.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        written.append(p)

        doc = [
            f"# {entry['name']}",
            "",
            entry["summary"],
            "",
            "**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy",
            f"this folder into the backend's `jarvis_plugins\\` folder (or run",
            f"`scripts\\add-plugin.ps1 -Name {entry['name']}`) and restart Jarvis.",
            "",
            f"- Module the loader calls: `{entry['module']}.install()`"
            + (" (takes the core's Handler)" if entry["install"] == "handler" else " (takes nothing)"),
            f"- The patch this replaces: `backend/{entry['patch']}`",
            f"- Position in the old patch stack: {entry['order']} of {data['patch_count']}",
            "",
            "The module itself is one of the ones this repository already ships",
            "(`backend/" + entry["module"] + ".py`), copied into the backend by",
            "`scripts/apply-patches.ps1` exactly as before. This folder does not",
            "change it.",
            "",
        ]
        p = folder / "README.md"
        p.write_text("\n".join(doc), encoding="utf-8")
        written.append(p)
    return written


def write_index(data: dict) -> Path:
    rows = ["| # | Drop-in module | What it does | Replaces |", "|---|---|---|---|"]
    for entry in data["entries"]:
        if entry["bucket"] == "plug-in":
            rows.append(f"| {entry['order']} | `{entry['name']}` | {entry['summary']} "
                        f"| `{entry['patch']}` |")
    core = [e for e in data["entries"] if e["bucket"] in ("core", "missing")]
    core_rows = ["| Patch | Why it stays in the core |", "|---|---|"]
    for entry in core:
        core_rows.append(f"| `{entry['patch']}` | {entry['why']} |")

    text = f"""# Plug-and-play modules

Generated by `tools/gen_plugin_catalogue.py` from the patch stack in
`scripts/apply-patches.ps1`. Do not edit by hand.

Jarvis's optional features used to arrive as a module **plus** a patch that
adds one line to `jarvis_hud.py` calling that module. The loader in
[`loader/`](loader/) makes that call itself, so the module becomes something
you drop in and take out.

- **{data['counts']['plug-in']} drop-in modules**, in [`ready/`](ready/) -
  one folder each, no core change.
- **{data['counts']['core']} core patches**, which still go on through
  `scripts/apply-patches.ps1` in its own order.

## The drop-in modules

{chr(10).join(rows)}

## What stays in the core

These are not optional. Most of them are safety or data-integrity fixes;
the rest edit lines the core already has, so they must be applied in the
stack's order and cannot be moved into a folder.

{chr(10).join(core_rows)}

## Adding and removing one

```powershell
# see what is installed and what is available
powershell -ExecutionPolicy Bypass -File .\\scripts\\list-plugins.ps1

# add one
powershell -ExecutionPolicy Bypass -File .\\scripts\\add-plugin.ps1 -Name news

# take it back out
powershell -ExecutionPolicy Bypass -File .\\scripts\\remove-plugin.ps1 -Name news
```

Both scripts copy or delete one folder inside the backend's
`jarvis_plugins\\` folder and nothing else. Removing a module never touches
the module file itself, so adding it again needs no re-install.
"""
    p = PLUGINS / "README.md"
    p.write_text(text, encoding="utf-8")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="fail if the catalogue on disk is stale; write nothing")
    args = ap.parse_args()

    data = build()
    body = json.dumps(data, indent=2) + "\n"
    index = None
    folders: list[tuple[Path, str]] = []
    for entry in data["entries"]:
        if entry["bucket"] != "plug-in":
            continue
        folders.append((PLUGINS / "ready" / entry["name"] / "plugin.json",
                        json.dumps({
                            "name": entry["name"], "summary": entry["summary"],
                            "module": entry["module"], "install": entry["install"],
                            "replaces_patch": entry["patch"],
                            "stack_order": entry["order"],
                        }, indent=2) + "\n"))

    if args.check:
        stale = []
        reg = PLUGINS / "registry.json"
        if not reg.is_file() or reg.read_text(encoding="utf-8") != body:
            stale.append(str(reg.relative_to(ROOT)))
        for path, text in folders:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                stale.append(str(path.relative_to(ROOT)))
        if stale:
            print("plug-in catalogue is stale; run: py -3 tools/gen_plugin_catalogue.py")
            for s in stale[:10]:
                print("  ", s)
            return 1
        print(f"plug-in catalogue is up to date "
              f"({data['counts']['plug-in']} drop-in, {data['counts']['core']} core)")
        return 0

    PLUGINS.mkdir(exist_ok=True)
    (PLUGINS / "registry.json").write_text(body, encoding="utf-8")
    write_plugin_folders(data)
    index = write_index(data)

    print(f"wrote plugins/registry.json - {data['patch_count']} patches: "
          f"{data['counts']['plug-in']} drop-in, {data['counts']['core']} core"
          + (f", {data['counts']['missing']} missing" if data["counts"]["missing"] else ""))
    for entry in data["entries"]:
        if entry["bucket"] == "plug-in":
            print(f"  ready/{entry['name']:<22} {entry['module']}.install()")
    if index:
        print(f"wrote {index.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
