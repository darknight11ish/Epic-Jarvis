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
  4a. every folder under `plugins/ready/` is accounted for - either a patch's
     generated mirror or a `plugin.json` of its own - so no real drop-in can be
     left out of the catalogue again (ten of them were until 2026-10-28);
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
  8. the loader's own suite AND the catalogue's own suite pass, in this
     process, with no owner's PC and no network.

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

    # --- 4a. every plugins/ready folder is accounted for ------------------
    # Ten real drop-in folders (receipts, skill-hub, vault, voiceprint,
    # notion-obsidian, media-index, sandbox, self-improve, auto-router and
    # vault-organizer) were in NEITHER the registry nor plugins/README.md
    # until 2026-10-28: the generator built its list from `$PATCHES`, and
    # those ten have no patch. They are read from their own plugin.json now;
    # a folder the generator cannot account for is refused (its `unaccounted`
    # list) and is a failure here too - never skipped.
    ready_dir = PLUGINS / "ready"
    folder_entries = data.get("folders", [])
    unaccounted = built.get("unaccounted", [])
    check("folders: the generator can account for every folder in plugins/ready/",
          not unaccounted,
          "\n".join(f"{u.get('folder')}: {u.get('why')}" for u in unaccounted)
          or "run: py -3 tools/gen_plugin_catalogue.py")
    ready_names = ({c.name for c in ready_dir.iterdir() if c.is_dir()}
                   if ready_dir.is_dir() else set())
    accounted = ({e["name"] for e in drop_ins}
                 | {f.get("name") for f in folder_entries})
    check("folders: every folder on disk is in one of the catalogue's two lists",
          ready_names == accounted,
          f"on disk but not listed: {sorted(ready_names - accounted)}\n"
          f"listed but not on disk: {sorted(accounted - ready_names)}")
    check("folders: the counts add up - patch-backed + no-patch = every folder",
          data.get("folder_count") == len(folder_entries)
          and data.get("ready_count") == len(drop_ins) + len(folder_entries)
          and len(ready_names) == data.get("ready_count"),
          f"folder_count={data.get('folder_count')} "
          f"ready_count={data.get('ready_count')} listed={len(folder_entries)} "
          f"on_disk={len(ready_names)} patch_backed={len(drop_ins)}")
    folder_bad: list[str] = []
    for f in folder_entries:
        manifest = ready_dir / str(f.get("name")) / "plugin.json"
        if not manifest.is_file():
            folder_bad.append(f"{f.get('name')}: its folder or plugin.json is missing")
            continue
        try:
            m = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            folder_bad.append(f"{f.get('name')}: plugin.json will not parse "
                              f"({type(exc).__name__})")
            continue
        for key in ("name", "module", "install", "stack_order", "summary"):
            if m.get(key) != f.get(key):
                folder_bad.append(f"{f.get('name')}: {key} disagrees with its "
                                  f"plugin.json ({m.get(key)!r} vs {f.get(key)!r})")
        if "replaces_patch" in m:
            folder_bad.append(f"{f.get('name')}: it names a patch, so the "
                              f"patch's own row belongs in `entries`, not `folders`")
    check("folders: every no-patch row is its own plugin.json, and names no patch",
          not folder_bad, "\n".join(folder_bad))

    # --- 4b. folders that replace NO patch ---------------------------------
    # The generator now lists those folders under `data["folders"]` (4a). This
    # is the second, independent check that each is loadable: the module it
    # names is in `backend/`, has the `install()` the loader calls, and is one
    # `apply-patches.ps1` copies in, because a folder whose module never
    # reaches the PC loads nothing.
    catalogue_folders = {e["name"] for e in drop_ins}
    shipped = set(ps1_shipped())
    extra_bad: list[str] = []
    for child in sorted(ready_dir.iterdir()) if ready_dir.is_dir() else []:
        if not child.is_dir() or child.name in catalogue_folders:
            continue
        manifest = child / "plugin.json"
        if not manifest.is_file():
            extra_bad.append(f"{child.name}: plugins/ready/{child.name}/plugin.json is missing")
            continue
        try:
            m = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            extra_bad.append(f"{child.name}: plugin.json will not parse ({type(exc).__name__})")
            continue
        module = str(m.get("module") or "")
        if not m.get("name") or not module or m.get("install") not in ("handler", "none"):
            extra_bad.append(f"{child.name}: plugin.json needs name, module and "
                             f"install (handler|none)")
        elif "replaces_patch" in m:
            extra_bad.append(f"{child.name}: it names a patch, so the catalogue should own it - "
                             f"run: py -3 tools/gen_plugin_catalogue.py")
        elif not (BACKEND / f"{module}.py").is_file():
            extra_bad.append(f"{child.name}: backend/{module}.py is missing")
        elif "def install(" not in (BACKEND / f"{module}.py").read_text(
                encoding="utf-8", errors="replace"):
            extra_bad.append(f"{child.name}: {module} has no install()")
        elif not isinstance(m.get("stack_order"), int):
            extra_bad.append(f"{child.name}: stack_order must be a whole number")
        elif f"{module}.py" not in shipped:
            extra_bad.append(f"{child.name}: {module}.py is not in $SHIPPED, so "
                             f"apply-patches.ps1 never copies it to the PC and the "
                             f"folder would load nothing")
    check("drop-ins: a folder that replaces no patch is sound and loadable",
          not extra_bad, "\n".join(extra_bad))

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
        # install block into the CHAIN the hook itself sits in. That is not
        # simply the patch listed above it: gate-risk-rows.patch sits between
        # them and changes jarvis_gate.py, touching none of these lines.
        #
        # AND IT IS NOT SIMPLY "the last one that adds a `.install(Handler`
        # line" EITHER (2026-10-11). picture-card.patch is listed immediately
        # before the hook and adds that call, but it adds it OUTSIDE the
        # chain, on the owner's own lines just past the banner - its own
        # comment says why ("every install block above writes into the chain
        # that ends at `# Before the main socket`, so a block added in the
        # middle of it leaves the next patch's hunk without its context").
        # Reading the list alone called that patch the hook's neighbour, and
        # the two checks below reported a defect in two patches that are both
        # right: the whole stack applies, too (_stack.stand_in("jarvis_hud.py")
        # invents nothing for either of them).
        #
        # What actually says "writes INTO the chain": every block in the chain
        # is appended to the block before it, so the patch's block lands
        # directly after a line ANOTHER install-block patch wrote into
        # jarvis_hud.py. Read from the patch text, not from the list order -
        # and only from its jarvis_hud.py half, because a patch that also
        # touches jarvis_gate.py (uncensored-optins.patch does) would
        # otherwise be read as if its first block were the HUD one.
        def hud_hunks(name: str):
            """(added, lands_after) for this patch's jarvis_hud.py half.

            `lands_after` is the LAST leading context line before a batch of
            added lines: a patch may add non-chain hunks (the active-lane
            helper at the top of jarvis_hud.py) before the install block that
            appends to the chain, and only the install block's own context
            says what the next patch anchors on. Reading only the first hunk's
            context made presets.patch look like it landed after the module
            top rather than after model-lanes.patch's block.
            """
            added, lead, in_hud, done = [], [], False, False
            for line in (BACKEND / name).read_text(encoding="utf-8").splitlines():
                if line.startswith("@@"):
                    done = False
                    continue
                if line.startswith(("---", "+++")):
                    if line.startswith("+++"):
                        in_hud = line.split()[1] == "b/jarvis_hud.py"
                    continue
                if not in_hud:
                    continue
                if line.startswith("+"):
                    added.append(line[1:])
                    done = True
                elif not done and line.startswith(" ") and line.strip():
                    lead.append(line[1:])
            return added, (lead[-1] if lead else "")

        writers = {}
        for name in listed[:listed.index("plugin-loader.patch")]:
            added, line_above = hud_hunks(name)
            if any(".install(Handler" in l for l in added):
                writers[name] = (added, line_above)
        written = {n: v[0] for n, v in writers.items()}
        above = None
        for name in reversed(list(writers)):
            line_above = writers[name][1]
            if line_above and any(line_above in written[other]
                                  for other in writers if other != name):
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

    # --- 8b. the catalogue's own suite ------------------------------------
    # The pin against a silent skip: a plugins/ready folder that is neither a
    # patch's mirror nor a complete no-patch manifest must be REPORTED, and the
    # committed tree must account for all 37. The suite proves both, and a
    # synthetic folder in a temporary plugins/ is how the refusal is exercised.
    spec = importlib.util.spec_from_file_location(
        "test_plugin_catalogue", BACKEND / "test_plugin_catalogue.py")
    cmod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cmod)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for name, fn in sorted(vars(cmod).items()):
            if name.startswith("t_") and callable(fn):
                try:
                    fn()
                except Exception as exc:  # noqa: BLE001
                    cmod.FAILED.append(name)
                    cmod.check(f"{name} raised", False, f"{type(exc).__name__}: {exc}")
    check("catalogue: its own suite passes here (every ready folder accounted for)",
          not cmod.FAILED,
          "failed: " + ", ".join(cmod.FAILED) if cmod.FAILED else "")
    print(f"        ({len(cmod.PASSED)} catalogue checks passed)")

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
