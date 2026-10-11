"""jarvis_plugins.py - drop-in modules: put a folder in, restart, the feature is on.

WHAT THIS IS FOR

Every optional Jarvis feature arrives as two things: a module copied beside
`jarvis_hud.py`, and a patch that adds ONE line to `jarvis_hud.py` calling
that module's own `install()`. The module already wraps the Handler and
serves its own routes; the patch exists only to make that call.

This module makes the call instead, for every module in a folder. So a
feature whose only wiring was that one call no longer needs a patch at all:
drop its folder into `jarvis_plugins\\` beside `jarvis_hud.py`, restart
Jarvis, and it is on. Take the folder out and it is off.

    jarvis_hud.py
    jarvis_news.py          <- the module this repository already ships
    jarvis_plugins\
        news\
            plugin.json     <- {"name": "news", "module": "jarvis_news", ...}
            README.md

`plugins/registry.json` in this repository lists which features this works
for, and why each of the others still needs its patch (a gate entry, or an
edit to the core's own code). `tools/gen_plugin_catalogue.py` writes it from
the patch stack itself.

HOW IT IS SWITCHED ON

`plugins/loader/plugin-loader.patch` adds one call at start-up, in the same
place and the same shape as every other feature's call:

    try:
        import jarvis_plugins
        print(jarvis_plugins.install(Handler, origin_ok=_origin_ok,
                                     token_ok=_token_ok, read_body=_read_body))
    except Exception as exc:
        ...

That patch is applied ONCE. After that, adding or removing a feature is a
folder, not a patch.

WHAT THIS DOES NOT DO

- It does not read, write or move any module file. The module itself is
  copied in by `scripts/apply-patches.ps1` exactly as before, and is never
  changed by this loader or by adding a folder.
- It does not approve anything, reach the network or start a program. It
  calls each module's own `install()` with the core's own three callbacks,
  which is precisely what the patch it replaces did.
- It does not weaken anything. A feature that also puts an entry in the
  approval gate's tables still needs its patch, and this loader does not
  invent those entries: a missing `_RISK` row would make an action skip
  Windows Hello, which is the safe side to stay on.

ONE RULE WORTH KNOWING

A folder in `jarvis_plugins\\` is code that runs inside the backend process
at start-up, with the same trust as `jarvis_hud.py` itself - anything that
could write that folder could already edit the backend. Two things follow,
and both are deliberate: the folder must sit beside `jarvis_hud.py` (a
`JARVIS_PLUGINS_DIR` pointing somewhere else is honoured only when it is an
absolute path that exists), and every load, skip and failure is printed in
the start-up banner so nothing arrives unnoticed.

Standard library only. No network, no subprocess, no file writes.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

#: The folder, beside `jarvis_hud.py`, that drop-in modules live in.
DIR_NAME = "jarvis_plugins"

#: Set this to use a different folder. It must be an absolute path.
DIR_ENV = "JARVIS_PLUGINS_DIR"

#: The three callbacks the core hands every install(), unchanged.
CTX_KEYS = ("origin_ok", "token_ok", "read_body")

_ARMED = False
_STATE: dict = {"loaded": [], "skipped": [], "failed": [], "dir": None}


def plugins_dir(here: Path | None = None) -> Path:
    """Where drop-in modules are looked for: beside this file by default."""
    override = os.environ.get(DIR_ENV, "").strip()
    if override:
        p = Path(override)
        if p.is_absolute():
            return p
        # A relative override is refused on purpose: the folder must be the
        # one next to jarvis_hud.py, not wherever the process happens to be.
    base = here if here is not None else Path(__file__).resolve().parent
    return base / DIR_NAME


def discover(folder: Path | None = None) -> list:
    """Every drop-in module in the folder, in the order the patch stack had
    them (so the wrapping order, and therefore the route precedence, is the
    same as it was when each was a patch).

    A folder with no readable `plugin.json`, or one naming nothing, is
    skipped and named in `status()` - never guessed at."""
    folder = folder or plugins_dir()
    found = []
    if not folder.is_dir():
        return found
    for child in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        manifest = child / "plugin.json"
        if not manifest.is_file():
            found.append({"name": child.name, "dir": child,
                          "error": "no plugin.json in the folder"})
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            found.append({"name": child.name, "dir": child,
                          "error": f"plugin.json will not parse ({type(exc).__name__})"})
            continue
        if not isinstance(data, dict):
            found.append({"name": child.name, "dir": child,
                          "error": "plugin.json is not an object"})
            continue
        entry = dict(data)
        entry.setdefault("name", child.name)
        entry["dir"] = child
        if not entry.get("module"):
            entry["error"] = "plugin.json names no module"
        if (child / "disabled").exists() or entry.get("enabled") is False:
            entry["disabled"] = True
        found.append(entry)
    found.sort(key=lambda e: (e.get("stack_order", 10_000), str(e.get("name", ""))))
    return found


def _install_one(entry: dict, ctx: dict) -> str:
    """Call the module's own install(), exactly as its patch did."""
    module = importlib.import_module(entry["module"])
    install = getattr(module, "install", None)
    if not callable(install):
        raise AttributeError(f"{entry['module']} has no install()")
    if entry.get("install") == "none":
        line = install()
    else:
        line = install(ctx["handler_cls"], origin_ok=ctx["origin_ok"],
                       token_ok=ctx["token_ok"], read_body=ctx["read_body"])
    return line if isinstance(line, str) else f"{entry['name']} installed"


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls` with every drop-in module in the folder.

    Same shape as every other module's install(): the core passes its own
    Handler and its own three checks, and this returns the lines the
    start-up banner prints. A module that fails is named and skipped; the
    others still load, and Jarvis still starts."""
    global _ARMED
    ctx = {"handler_cls": handler_cls, "origin_ok": origin_ok,
           "token_ok": token_ok, "read_body": read_body}
    folder = plugins_dir()
    _STATE["dir"] = str(folder)

    entries = discover(folder)
    if not entries:
        _ARMED = True
        _STATE["loaded"] = []
        return (f"  plugins    none - put a folder in {folder} to add a module\n"
                f"             (nothing to do if you meant to have no drop-in modules)")

    lines = []
    loaded, skipped, failed = [], [], []
    for entry in entries:
        name = str(entry.get("name"))
        if entry.get("error"):
            failed.append((name, entry["error"]))
            continue
        if entry.get("disabled"):
            skipped.append((name, "switched off (disabled marker)"))
            continue
        try:
            line = _install_one(entry, ctx)
        except Exception as exc:
            failed.append((name, f"{type(exc).__name__}: {exc}"))
            continue
        loaded.append(name)
        lines.append(f"  plugins      {name:<10} {line.strip()}")

    on = len(loaded)
    off = len(skipped) + len(failed)
    head = (f"  plugins    drop-in modules: {on} on"
            + (f", {off} not" if off else "")
            + f"  ({folder})")
    for name, why in skipped:
        lines.append(f"  plugins      {name:<10} off - {why}")
    for name, why in failed:
        lines.append(f"  plugins      {name:<10} NOT ON - {why}")

    _STATE["loaded"] = loaded
    _STATE["skipped"] = [n for n, _ in skipped]
    _STATE["failed"] = [{"name": n, "why": w} for n, w in failed]
    _ARMED = True
    return "\n".join([head] + lines)


def status() -> dict:
    """What the last install() did - for the self test and the suites."""
    return {"armed": _ARMED, "dir": _STATE["dir"],
            "loaded": list(_STATE["loaded"]),
            "skipped": list(_STATE["skipped"]),
            "failed": list(_STATE["failed"])}


def available(folder: Path | None = None) -> list:
    """Names of the drop-in modules in the folder, without installing any."""
    out = []
    for entry in discover(folder):
        if entry.get("error"):
            out.append({"name": entry.get("name"), "ok": False, "why": entry["error"]})
            continue
        out.append({
            "name": entry.get("name"),
            "ok": True,
            "module": entry.get("module"),
            "summary": entry.get("summary", ""),
            "disabled": bool(entry.get("disabled")),
        })
    return out


def _reset_for_tests() -> None:
    global _ARMED
    _ARMED = False
    _STATE.update({"loaded": [], "skipped": [], "failed": [], "dir": None})
    for name in [n for n in sys.modules if n.startswith("_plugintest_")]:
        del sys.modules[name]
