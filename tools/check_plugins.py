#!/usr/bin/env python3
"""Check the plug-and-play system: one command, everything that can be proven
here.

What it checks, and why each one matters:

  1. the catalogue on disk matches the patch stack (`gen_plugin_catalogue.py
     --check`), so no one is reading a stale list of what is drop-in;
  2. every patch in `$PATCHES` is in exactly one bucket - nothing added to
     the stack silently stops being catalogued;
  3. every drop-in module named really is in `backend/` and really has an
     `install()`, which is the only thing the loader calls;
  4. every drop-in folder exists, and its manifest agrees with the catalogue;
  5. `backend/plugin-loader.patch` is well formed: hunk counts add up, it
     targets `jarvis_hud.py`, its context is the output of the patch above it
     in the stack (`tutorials.patch`), and it adds exactly the one import and
     the one call - nothing else;
  6. it is the LAST entry in `$PATCHES`, which is the repo's own rule for a
     new patch;
  7. `jarvis_plugins.py` is in both shipped-modules lists (the script's
     `$SHIPPED` and `backend/_where.py`'s `SHIPPED`) - they are checked
     against each other by test_shipped_modules.py, and a module in only one
     of them never reaches the PC;
  8. the loader's own suite passes, in this process, with no owner's PC and
     no network.

Run:  py -3 tools/check_plugins.py
Exit: 0 when everything passes, 1 otherwise.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PLUGINS = ROOT / "plugins"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT / "tools"))

PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    (PASSED if cond else FAILED).append((name, detail))
    print(f"{'ok   ' if cond else 'FAIL '} {name}")
    if detail and not cond:
        for line in detail.splitlines():
            print(f"        {line}")
    return cond


def ps1_patches() -> list[str]:
    """The stack exactly as the suites see it: `_stack.order()` resolves the
    rebuilt-module substitutions, so its list is the one to check against."""
    sys.path.insert(0, str(BACKEND))
    import _stack
    return _stack.order()


def ps1_shipped() -> list[str]:
    """`$SHIPPED`'s module names. Each line is `'name.py'  # why`, so the name
    is the first quoted run on the line - not the whole line."""
    text = (ROOT / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = text.index("$SHIPPED = @(")
    body = text[start:text.index("\n)", start)]
    return re.findall(r"^\s*'([^']+)'", body, re.M)


def parse_hunks(text: str) -> list[dict]:
    """A minimal unified-diff reader: header counts and body lines."""
    hunks, cur = [], None
    for line in text.splitlines():
        if line.startswith("@@ "):
            m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            cur = {"old": int(m.group(2) or 1), "new": int(m.group(4) or 1),
                   "body": []}
            hunks.append(cur)
            continue
        if cur is None or line.startswith(("---", "+++")):
            continue
        if line.startswith(("-", "+", " ")) or line == "":
            cur["body"].append(line)
    return hunks


def main() -> int:
    # --- 1. the catalogue is current ---------------------------------------
    spec = importlib.util.spec_from_file_location(
        "gen_plugin_catalogue", ROOT / "tools" / "gen_plugin_catalogue.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    built = gen.build()
    body = json.dumps(built, indent=2) + "\n"
    registry = PLUGINS / "registry.json"
    check("catalogue: plugins/registry.json exists", registry.is_file())
    if registry.is_file():
        check("catalogue: it matches the patch stack (re-run the generator if not)",
              registry.read_text(encoding="utf-8") == body,
              "run: py -3 tools/gen_plugin_catalogue.py")
    data = json.loads(registry.read_text(encoding="utf-8")) if registry.is_file() else {"entries": []}
    entries = data.get("entries", [])
    drop_ins = [e for e in entries if e.get("bucket") == "plug-in"]

    # --- 2. every patch is bucketed exactly once ---------------------------
    listed = ps1_patches()
    catalogued = [e["patch"] for e in entries]
    check("patches: the catalogue covers every patch in $PATCHES",
          len(catalogued) == len(listed) and sorted(catalogued) == sorted(listed),
          f"{len(catalogued)} catalogued vs {len(listed)} in the script")
    check("patches: nothing appears twice",
          len(set(catalogued)) == len(catalogued))
    check("patches: every bucket is one we know",
          all(e.get("bucket") in ("plug-in", "core", "missing") for e in entries),
          str(sorted({e.get("bucket") for e in entries})))
    check("patches: there are drop-in modules to speak of", len(drop_ins) > 0)

    # --- 3 & 4. the drop-in modules and their folders ----------------------
    bad_module, bad_folder = [], []
    for e in drop_ins:
        module = BACKEND / f"{e['module']}.py"
        if not module.is_file():
            bad_module.append(f"{e['name']}: backend/{e['module']}.py is missing")
        elif "def install(" not in module.read_text(encoding="utf-8", errors="replace"):
            bad_module.append(f"{e['name']}: {e['module']} has no install()")
        folder = PLUGINS / "ready" / e["name"]
        manifest = folder / "plugin.json"
        if not manifest.is_file():
            bad_folder.append(f"{e['name']}: plugins/ready/{e['name']}/plugin.json is missing")
        else:
            m = json.loads(manifest.read_text(encoding="utf-8"))
            if m.get("module") != e["module"] or m.get("replaces_patch") != e["patch"]:
                bad_folder.append(f"{e['name']}: plugin.json disagrees with the catalogue")
    check("drop-ins: every module is really in backend/ with an install()",
          not bad_module, "\n".join(bad_module))
    check("drop-ins: every folder is there and agrees with the catalogue",
          not bad_folder, "\n".join(bad_folder))

    # --- 5 & 6. the hook patch --------------------------------------------
    hook = BACKEND / "plugin-loader.patch"
    check("hook: backend/plugin-loader.patch is there", hook.is_file())
    if hook.is_file():
        text = hook.read_text(encoding="utf-8")
        hunks = parse_hunks(text)
        counts_ok = True
        for h in hunks:
            old = sum(1 for l in h["body"] if l.startswith((" ", "-")))
            new = sum(1 for l in h["body"] if l.startswith((" ", "+")))
            if old != h["old"] or new != h["new"]:
                counts_ok = False
        check("hook: one hunk, and its line counts match its header",
              len(hunks) == 1 and counts_ok,
              f"{len(hunks)} hunk(s)")
        check("hook: it targets jarvis_hud.py",
              text.startswith("--- a/jarvis_hud.py") and "+++ b/jarvis_hud.py" in text)

        # Its context is the output of the last patch BEFORE it that writes an
        # install block into jarvis_hud.py. That is not simply the patch listed
        # above it: gate-risk-rows.patch sits between them and changes
        # jarvis_gate.py, touching none of these lines.
        above = None
        for name in reversed(listed[:listed.index("plugin-loader.patch")]):
            text_above = (BACKEND / name).read_text(encoding="utf-8")
            if any(".install(Handler" in l for l in text_above.splitlines()
                   if l.startswith("+") and not l.startswith("+++")):
                above = name
                break
        check("hook: an install block is what it anchors on", above is not None)
        if above:
            above_text = (BACKEND / above).read_text(encoding="utf-8")
            above_added = [l[1:] for l in above_text.splitlines()
                           if l.startswith("+") and not l.startswith("+++")]
            above_context = [l[1:] for l in above_text.splitlines()
                             if l.startswith(" ") and l.strip()]
            body = hunks[0]["body"] if hunks else []
            leading = body[:2]
            expect_lead = [" " + above_added[-2], " " + above_added[-1]]
            check(f"hook: its context is {above}'s own last two added lines",
                  leading == expect_lead,
                  f"got {leading!r}\nwant {expect_lead!r}")
            trailing = [l for l in body if l.startswith(" ")]
            check("hook: the line after it is the one the whole stack leaves there",
                  bool(trailing) and trailing[-1] == " " + above_context[-1],
                  f"got {trailing[-1] if trailing else None!r}")
        added = [l[1:] for l in (hunks[0]["body"] if hunks else []) if l.startswith("+")]
        check("hook: it adds one import and one call, and nothing else that runs",
              sum(1 for l in added if l.strip() == "import jarvis_plugins") == 1
              and sum(1 for l in added if "jarvis_plugins.install(" in l) == 1,
              "\n".join(added))
        check("hook: the call takes the core's own three callbacks",
              any("origin_ok=" in l for l in added)
              and any("token_ok=" in l for l in added)
              and any("read_body=" in l for l in added))
        check("hook: it is the LAST entry in $PATCHES",
              listed[-1] == "plugin-loader.patch", listed[-1])

    # --- 7. shipped in both lists -----------------------------------------
    in_script = "jarvis_plugins.py" in ps1_shipped()
    where = (BACKEND / "_where.py").read_text(encoding="utf-8")
    in_where = '"jarvis_plugins.py"' in where
    check("shipped: it is in scripts/apply-patches.ps1's $SHIPPED", in_script)
    check("shipped: it is in backend/_where.py's SHIPPED", in_where)

    # --- 8. the loader's own suite ----------------------------------------
    spec = importlib.util.spec_from_file_location(
        "test_jarvis_plugins", BACKEND / "test_jarvis_plugins.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for name, fn in sorted(vars(mod).items()):
            if name.startswith("t_") and callable(fn):
                try:
                    fn()
                except Exception as exc:  # noqa: BLE001
                    mod.FAILED.append(name)
                    mod.check(f"{name} raised", False, f"{type(exc).__name__}: {exc}")
    check("loader: its own suite passes here, with no owner's PC",
          not mod.FAILED,
          "failed: " + ", ".join(mod.FAILED) if mod.FAILED else "")
    print(f"        ({len(mod.PASSED)} loader checks passed)")

    print()
    if FAILED:
        print(f"{len(PASSED)} passed, {len(FAILED)} FAILED")
        for name, _ in FAILED:
            print(f"  - {name}")
        return 1
    print(f"{len(PASSED)} passed, 0 failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
