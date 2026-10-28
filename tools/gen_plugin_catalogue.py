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

A folder that replaces NO patch is still a drop-in, so it is listed too: its
own `plugin.json` is the manifest (a feature born as a folder - the first was
`plugins/ready/receipts`, 2026-10-14), and `build()` reads it into `folders`.
This tool does not write such a folder, because the folder IS the feature's
wiring; but the registry and `plugins/README.md` count it, so the catalogue and
`plugins/ready/` agree. A folder that is neither a patch's mirror nor a
complete no-patch manifest goes into `unaccounted`, and the catalogue refuses
rather than skipping it. That silence is exactly how ten real drop-ins -
receipts, skill-hub, vault, voiceprint, notion-obsidian, media-index, sandbox,
self-improve, auto-router and vault-organizer - appeared in no catalogue at
all until 2026-10-28.

Run:  py -3 tools/gen_plugin_catalogue.py [--check]
      --check fails instead of writing, the way the other gen_* tools do.

--check COMPARES EVERY FILE LISTED ABOVE, the two README kinds included
(2026-10-11). It did not: `registry.json` and the `plugin.json` files were
compared and the READMEs were not, so every one of them could - and did -
still say "of 134" against a stack of 136, with this check green. The four
kinds come from one list, `owned_files()`, so a file the writer writes is a
file the check compares.
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

#: What a `plugin.json` may say its `install()` takes: the core's Handler, or
#: nothing (a module with its own scheduler or registry hook).
INSTALL_KINDS = ("handler", "none")

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


def folder_manifest(folder: Path) -> tuple[dict | None, str]:
    """Read one `plugins/ready/<name>/plugin.json`.

    `(data, why)` - `data` is the object, or None with a plain-words reason
    this folder cannot be a drop-in the catalogue lists. It only reads; the
    caller decides whether that is a refusal.
    """
    manifest = folder / "plugin.json"
    if not manifest.is_file():
        return None, "there is no plugin.json, so nothing says what it would load"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - the reason is the point
        return None, f"plugin.json will not parse ({type(exc).__name__})"
    if not isinstance(data, dict):
        return None, "plugin.json is not a JSON object"
    return data, ""


def folder_only_entries(plug_in_names: set[str]) -> tuple[list[dict], list[dict]]:
    """Every `ready/<name>/` folder that replaces NO patch, and every folder
    that is neither one of those nor a generated plug-in.

    A folder is a drop-in in its own right when its manifest has `name`,
    `module`, `install`, `stack_order` and `summary`, and no `replaces_patch`:
    the feature was born as a folder, so there is no patch for `build()` to
    mirror it from. Anything else is returned in `unaccounted` instead of being
    skipped - that is the pin against the failure this function exists to end:
    ten real drop-in folders appeared in no catalogue at all until 2026-10-28.
    """
    ready = PLUGINS / "ready"
    folders: list[dict] = []
    unaccounted: list[dict] = []
    if not ready.is_dir():
        return folders, unaccounted
    for child in sorted(ready.iterdir()):
        if not child.is_dir() or child.name in plug_in_names:
            continue
        data, why = folder_manifest(child)
        if data is None:
            unaccounted.append({"folder": child.name, "why": why})
            continue
        if data.get("replaces_patch"):
            unaccounted.append({
                "folder": child.name,
                "why": (f"its plugin.json names replaces_patch "
                        f"{data['replaces_patch']!r}, which is not a drop-in in "
                        f"the patch stack any more; run the generator WITHOUT "
                        f"--check to prune a stale mirror"),
            })
            continue
        problems = []
        if data.get("name") != child.name:
            problems.append("`name` does not match the folder")
        if not isinstance(data.get("module"), str) or not data["module"]:
            problems.append("`module` is missing or not text")
        if data.get("install") not in INSTALL_KINDS:
            problems.append('`install` must be "handler" or "none"')
        if not isinstance(data.get("stack_order"), int):
            problems.append("`stack_order` must be a whole number")
        if not isinstance(data.get("summary"), str) or not data["summary"].strip():
            problems.append("`summary` is missing or empty")
        if problems:
            unaccounted.append({"folder": child.name, "why": "; ".join(problems)})
            continue
        folders.append({
            "name": child.name,
            "module": data["module"],
            "install": data["install"],
            "stack_order": data["stack_order"],
            "summary": data["summary"].strip(),
            "why": "born as a folder: it replaces no patch",
        })
    folders.sort(key=lambda f: (f["stack_order"], f["name"]))
    return folders, unaccounted


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
    folders, unaccounted = folder_only_entries({r["name"] for r in plug_ins})
    return {
        "about": (
            "Generated by tools/gen_plugin_catalogue.py from $PATCHES in "
            "scripts/apply-patches.ps1 (the `entries`) and from the plugin.json "
            "of every plugins/ready folder that replaces no patch (the `folders`). "
            "Do not edit by hand; re-run the tool."
        ),
        "stack": "scripts/apply-patches.ps1",
        "patch_count": len(order),
        "counts": {
            "plug-in": len(plug_ins),
            "core": len([r for r in registry if r["bucket"] == "core"]),
            "missing": len([r for r in registry if r["bucket"] == "missing"]),
        },
        "folder_count": len(folders),
        "ready_count": len(plug_ins) + len(folders),
        "folders": folders,
        "unaccounted": unaccounted,
        "entries": registry,
    }


def plugin_manifest_text(entry: dict) -> str:
    """The exact body of one `ready/<name>/plugin.json`."""
    return json.dumps({
        "name": entry["name"],
        "summary": entry["summary"],
        "module": entry["module"],
        "install": entry["install"],
        "replaces_patch": entry["patch"],
        "stack_order": entry["order"],
    }, indent=2) + "\n"


def plugin_readme_text(entry: dict, patch_count: int) -> str:
    """The exact body of one `ready/<name>/README.md`."""
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
        f"- Position in the old patch stack: {entry['order']} of {patch_count}",
        "",
        "The module itself is one of the ones this repository already ships",
        "(`backend/" + entry["module"] + ".py`), copied into the backend by",
        "`scripts/apply-patches.ps1` exactly as before. This folder does not",
        "change it.",
        "",
    ]
    return "\n".join(doc)


def cell(text: str) -> str:
    """One markdown table cell: a pipe in the text must not split the row."""
    return " ".join(str(text).split()).replace("|", "\\|")


def index_text(data: dict) -> str:
    """The exact body of `plugins/README.md`."""
    rows = ["| # | Drop-in module | What it does | Replaces |", "|---|---|---|---|"]
    for entry in data["entries"]:
        if entry["bucket"] == "plug-in":
            rows.append(f"| {entry['order']} | `{entry['name']}` | {cell(entry['summary'])} "
                        f"| `{entry['patch']}` |")
    folder_rows = ["| Loader order | Drop-in module | What it does |", "|---|---|---|"]
    for entry in data["folders"]:
        folder_rows.append(f"| {entry['stack_order']} | `{entry['name']}` | "
                           f"{cell(entry['summary'])} |")
    core = [e for e in data["entries"] if e["bucket"] in ("core", "missing")]
    core_rows = ["| Patch | Why it stays in the core |", "|---|---|"]
    for entry in core:
        core_rows.append(f"| `{entry['patch']}` | {entry['why']} |")

    return f"""# Plug-and-play modules

Generated by `tools/gen_plugin_catalogue.py` from the patch stack in
`scripts/apply-patches.ps1` and from every `ready/<name>/plugin.json` that
replaces no patch. Do not edit by hand.

Jarvis's optional features used to arrive as a module **plus** a patch that
adds one line to `jarvis_hud.py` calling that module. The loader in
[`loader/`](loader/) makes that call itself, so the module becomes something
you drop in and take out.

- **{data['ready_count']} drop-in modules**, in [`ready/`](ready/) -
  one folder each, no core change:
  - **{data['counts']['plug-in']}** replace a patch, and are generated from it;
  - **{data['folder_count']}** replace no patch: they were born as folders, and
    their own `plugin.json` is the whole of their wiring.
- **{data['counts']['core']} core patches**, which still go on through
  `scripts/apply-patches.ps1` in its own order.

There is no third kind. Every folder under [`ready/`](ready/) is in one of the
two tables below, and `tools/check_plugins.py` fails if one is not - a folder
the catalogue cannot account for is refused, never silently left out.

## The drop-in modules that replace a patch

{chr(10).join(rows)}

## Drop-in modules with no patch of their own

These {data['folder_count']} were never patches. There is nothing in the core
to take out: the folder **is** that feature's wiring, and the module it names
is shipped by `scripts/apply-patches.ps1` like every other one. They are listed
here so the count above has one home; `tools/check_plugins.py` checks each one
too - its module is in `backend/`, it has the `install()` the loader calls, and
it is one `apply-patches.ps1` copies in.

{chr(10).join(folder_rows)}

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


def prune_ready(data: dict) -> list[str]:
    """Delete a `ready/<name>/` folder that is a STALE MIRROR of a patch.

    A folder stays while its patch is still a drop-in (`keep`). A folder that
    replaces NO patch is not this generator's to delete: it is the whole of
    that feature's wiring. Anything else - no manifest, a manifest that will
    not parse, a manifest without `replaces_patch` - is left exactly where it
    is and named in `unaccounted` instead (see `folder_only_entries`), so the
    generator refuses rather than deleting something a person may be working on.
    """
    ready = PLUGINS / "ready"
    keep = {e["name"] for e in data["entries"] if e["bucket"] == "plug-in"}
    folder_only = {f["name"] for f in data["folders"]}
    removed: list[str] = []
    if ready.is_dir():
        for child in sorted(ready.iterdir()):
            if (not child.is_dir() or child.name in keep
                    or child.name in folder_only):
                continue
            manifest = child / "plugin.json"
            if not manifest.is_file():
                continue
            try:
                manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(manifest_data, dict) and manifest_data.get("replaces_patch"):
                shutil.rmtree(child, ignore_errors=True)
                removed.append(child.name)
    return removed


def owned_files(data: dict) -> list[tuple[Path, str]]:
    """EVERY file this tool owns, as `(path, exact text)` - one list, used for
    both jobs: the write, and `--check`'s comparison (2026-10-11).

    That is the point of it. `--check` used to compare `registry.json` and the
    `plugin.json` files only, so `plugins/README.md` and every
    `ready/<name>/README.md` could fall behind the patch stack with the check
    still green - and by the time this was written they had: every one of them
    said "of 134" against a stack of 136, and the newest drop-in's folder had
    never been written at all. Two lists of "what this tool writes" is how that
    happens, so there is one.
    """
    out: list[tuple[Path, str]] = [
        (PLUGINS / "registry.json", json.dumps(data, indent=2) + "\n"),
        (PLUGINS / "README.md", index_text(data)),
    ]
    for entry in data["entries"]:
        if entry["bucket"] != "plug-in":
            continue
        folder = PLUGINS / "ready" / entry["name"]
        out.append((folder / "plugin.json", plugin_manifest_text(entry)))
        out.append((folder / "README.md", plugin_readme_text(entry, data["patch_count"])))
    return out


def print_unaccounted(unaccounted: list[dict], why: str) -> None:
    """Say, in plain words, which `ready/` folder the catalogue cannot list."""
    print(why)
    for item in unaccounted:
        print(f"  plugins/ready/{item['folder']}/: {item['why']}")
    print("  A folder under plugins/ready/ is either a drop-in named by a patch in")
    print("  $PATCHES, or a complete no-patch manifest: name, module, install")
    print("  (handler|none), stack_order, summary, and no replaces_patch.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="fail if the catalogue on disk is stale; write nothing")
    args = ap.parse_args()

    data = build()

    if args.check:
        owned = owned_files(data)
        stale = [str(path.relative_to(ROOT)) for path, text in owned
                 if not path.is_file() or path.read_text(encoding="utf-8") != text]
        if stale:
            print("plug-in catalogue is stale; run: py -3 tools/gen_plugin_catalogue.py")
            for s in stale[:10]:
                print("  ", s)
        if data["unaccounted"]:
            print_unaccounted(
                data["unaccounted"],
                "the plug-in catalogue cannot account for every folder under plugins/ready/:")
        if stale or data["unaccounted"]:
            return 1
        print(f"plug-in catalogue is up to date "
              f"({data['ready_count']} drop-in folders: "
              f"{data['counts']['plug-in']} patch-backed + "
              f"{data['folder_count']} with no patch; "
              f"{data['counts']['core']} core)")
        print(f"  ({len(owned)} file(s) compared - registry.json, README.md and "
              f"every generated ready/<name>/plugin.json AND README.md)")
        return 0

    PLUGINS.mkdir(exist_ok=True)
    for name in prune_ready(data):
        print(f"  pruned ready/{name} (its patch is no longer a drop-in)")
    if data["unaccounted"]:
        # A stale mirror just pruned may have been the only unaccounted folder.
        data = build()
    if data["unaccounted"]:
        print_unaccounted(
            data["unaccounted"],
            "refusing to write: the catalogue cannot account for every folder "
            "under plugins/ready/:")
        return 1
    for entry in data["folders"]:
        print(f"  kept   ready/{entry['name']} (a drop-in with no patch of its own)")
    owned = owned_files(data)
    for path, text in owned:
        path.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n" is not decoration: this repository is LF everywhere
        # (.gitattributes, `* text=auto eol=lf`), and the default newline=None
        # translates every "\n" to os.linesep on the way out - so on Windows
        # this wrote 50 files as CRLF. Measured 2026-10-14 on 4d1812b7: a second
        # run with no source change converted all 50 (registry.json 984 lines,
        # README.md 188) to CRLF and left `git status` showing every one of them
        # modified, while `--check` stayed GREEN - because path.read_text() at
        # the comparison above translates CRLF back to "\n" too, so the two
        # normalise to the same string and the drift is invisible. The same
        # defect was already fixed once in tools/gen_picture_card_patch.py,
        # whose comment says it in one line: "LF, not CRLF: this repository is
        # LF everywhere (.gitattributes says so)".
        path.write_text(text, encoding="utf-8", newline="\n")

    print(f"wrote plugins/registry.json - {data['patch_count']} patches: "
          f"{data['counts']['plug-in']} drop-in, {data['counts']['core']} core"
          + (f", {data['counts']['missing']} missing" if data["counts"]["missing"] else ""))
    for entry in data["entries"]:
        if entry["bucket"] == "plug-in":
            print(f"  ready/{entry['name']:<22} {entry['module']}.install()")
    print(f"       and {data['ready_count']} drop-in folders: "
          f"{data['counts']['plug-in']} generated + "
          f"{data['folder_count']} that replace no patch")
    print(f"wrote {len(owned)} file(s) under {PLUGINS.relative_to(ROOT)}/ - the "
          f"{data['counts']['plug-in']} ready/<name>/ folders with their own README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
