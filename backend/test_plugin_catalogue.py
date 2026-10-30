"""The plug-in catalogue must account for EVERY `plugins/ready/` folder.

WHY THIS EXISTS

Until 2026-10-28 `tools/gen_plugin_catalogue.py` built its list from
`$PATCHES` only. A folder that was born as a folder - a real drop-in with its
own `plugin.json` and no patch to mirror - was left out of
`plugins/registry.json` and out of `plugins/README.md`. Ten were:
`receipts`, `skill-hub`, `vault`, `voiceprint`, `notion-obsidian`,
`media-index`, `sandbox`, `self-improve`, `auto-router` and
`vault-organizer`. The README said "27 drop-in modules" while `ready/` held
37, and nothing failed: the generator's `--check` compared only the files it
wrote, so a folder it chose not to write could not be seen as stale.

WHAT THIS PINS

  - the committed tree accounts for every folder: 28 patch-backed drop-ins
    plus the twelve no-patch ones above (and that list is written down, so
    losing one is a failure rather than a smaller number);
  - a synthetic folder the catalogue cannot read - no manifest, a manifest
    that will not parse, or a complete one - is REPORTED in `unaccounted`,
    listed in `folders`, or pruned when it is a stale patch mirror, and never
    silently dropped;
  - the generator's write mode refuses a folder it cannot account for.

The three synthetic cases swap `gen.PLUGINS` for a temporary folder and put it
back in a `finally`: they prove the refusal path without touching the tree.

    python3 test_plugin_catalogue.py
"""
import importlib.util
import json
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
GEN = REPO / "tools" / "gen_plugin_catalogue.py"

FAILED, PASSED, SKIPPED = [], [], []

#: The no-patch drop-ins: the ten that were the whole of the 2026-10-28 gap,
#: plus `model-recommendations` (the 2026-10-28 advisor's own install block lives
#: in its backend module, so its folder replaces no patch) and `jarvis-calendar`
#: (the 2026-10-29 local calendar, whose routes come from its own install()).
#: They replace no patch, so `$PATCHES` cannot name them; their own
#: `plugin.json` is the manifest. Adding another is a catalogue-count change:
#: put it here too.
NO_PATCH = {
    "antislop",
    "google-calendar",
    # The app builder's last two steps (2026-10-30, JARVIS-API section 166):
    # `jarvis_android_builder.install()` answers its four routes, called by the
    # drop-in loader, so the folder is the whole of its wiring and no patch is
    # added to `jarvis_hud.py`.
    "android-builder",
    "jarvis-calendar",
    "auto-router",
    "media-index",
    "notion-obsidian",
    "receipts",
    "sandbox",
    "self-improve",
    "skill-hub",
    "vault",
    "vault-organizer",
    "voiceprint",
}


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def gen_module():
    spec = importlib.util.spec_from_file_location(
        "test_gen_plugin_catalogue", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ready_names(plugins: Path) -> set:
    ready = plugins / "ready"
    return ({p.name for p in ready.iterdir() if p.is_dir()}
            if ready.is_dir() else set())


def with_plugins(gen, plugins: Path, fn):
    """Run `fn()` while the generator's `PLUGINS` points at a temp folder."""
    old = gen.PLUGINS
    gen.PLUGINS = plugins
    try:
        return fn()
    finally:
        gen.PLUGINS = old


def t_every_ready_folder_is_in_the_catalogue():
    """The committed tree: no folder outside the two lists, and the ten
    no-patch drop-ins are the audited ones."""
    if not GEN.is_file():
        SKIPPED.append("the generator")
        print("skip  tools/gen_plugin_catalogue.py is not in this layout")
        return
    gen = gen_module()
    data = gen.build()
    on_disk = ready_names(gen.PLUGINS)
    listed = ({e["name"] for e in data["entries"] if e["bucket"] == "plug-in"}
              | {f["name"] for f in data["folders"]})
    check("catalogue: every plugins/ready folder is in one of the two lists",
          on_disk == listed,
          f"on disk but not listed: {sorted(on_disk - listed)}\n"
          f"listed but not on disk: {sorted(listed - on_disk)}")
    check("catalogue: the counts add up",
          data["ready_count"] == len(on_disk) == len(listed)
          and data["folder_count"] == len(data["folders"]),
          f"ready_count={data['ready_count']} on_disk={len(on_disk)} "
          f"listed={len(listed)} folder_count={data['folder_count']}")
    check("catalogue: nothing is unaccounted",
          not data["unaccounted"], str(data["unaccounted"]))
    check("catalogue: the ten no-patch drop-ins are the audited ones",
          {f["name"] for f in data["folders"]} == NO_PATCH,
          f"got {sorted(f['name'] for f in data['folders'])}")
    check("catalogue: every no-patch row is complete",
          all(f.get("module") and f.get("install") in ("handler", "none")
              and isinstance(f.get("stack_order"), int) and f.get("summary")
              and "replaces_patch" not in f
              for f in data["folders"]),
          str(data["folders"]))


def t_a_folder_with_no_manifest_is_reported():
    """A folder with no `plugin.json` cannot be a drop-in; it must be named,
    not skipped, and it must not be deleted."""
    if not GEN.is_file():
        SKIPPED.append("the generator")
        return
    gen = gen_module()
    with tempfile.TemporaryDirectory() as tmp:
        plugins = Path(tmp)
        stray = plugins / "ready" / "stray"
        stray.mkdir(parents=True)
        data = with_plugins(gen, plugins, gen.build)
        check("catalogue: a folder with no plugin.json is REPORTED",
              [u for u in data["unaccounted"] if u.get("folder") == "stray"],
              str(data["unaccounted"]))
        check("catalogue: it is not silently listed as a drop-in",
              "stray" not in {f["name"] for f in data["folders"]})
        removed = with_plugins(gen, plugins, lambda: gen.prune_ready(data))
        check("catalogue: it is NOT deleted, so a half-written feature survives",
              stray.is_dir() and removed == [], f"removed={removed}")


def t_a_broken_manifest_is_reported():
    """A manifest that will not parse is the case a bare try/except would
    swallow. It is reported in `unaccounted` by name."""
    if not GEN.is_file():
        SKIPPED.append("the generator")
        return
    gen = gen_module()
    with tempfile.TemporaryDirectory() as tmp:
        plugins = Path(tmp)
        folder = plugins / "ready" / "bad"
        folder.mkdir(parents=True)
        (folder / "plugin.json").write_text("{not json", encoding="utf-8")
        data = with_plugins(gen, plugins, gen.build)
        bad = [u for u in data["unaccounted"] if u.get("folder") == "bad"]
        check("catalogue: a manifest that will not parse is REPORTED, not swallowed",
              bad and "parse" in bad[0].get("why", ""), str(data["unaccounted"]))


def t_a_complete_no_patch_folder_is_listed():
    """The positive case: name, module, install, stack_order and summary, and
    no replaces_patch, is a drop-in the catalogue lists."""
    if not GEN.is_file():
        SKIPPED.append("the generator")
        return
    gen = gen_module()
    with tempfile.TemporaryDirectory() as tmp:
        plugins = Path(tmp)
        folder = plugins / "ready" / "kept"
        folder.mkdir(parents=True)
        (folder / "plugin.json").write_text(json.dumps({
            "name": "kept",
            "module": "jarvis_receipts",
            "install": "handler",
            "stack_order": 999,
            "summary": "a kept one.",
        }), encoding="utf-8")
        data = with_plugins(gen, plugins, gen.build)
        kept = [f for f in data["folders"] if f["name"] == "kept"]
        check("catalogue: a complete no-patch folder is listed",
              kept and kept[0]["module"] == "jarvis_receipts"
              and kept[0]["stack_order"] == 999, str(data["folders"]))
        check("catalogue: it is not unaccounted", not data["unaccounted"],
              str(data["unaccounted"]))


def t_a_stale_patch_mirror_is_pruned_not_refused():
    """A folder whose `replaces_patch` is no longer a drop-in is a stale
    mirror: the generator names it in `--check`, and write mode prunes it.
    This is what keeps an old folder from blocking every future run."""
    if not GEN.is_file():
        SKIPPED.append("the generator")
        return
    gen = gen_module()
    with tempfile.TemporaryDirectory() as tmp:
        plugins = Path(tmp)
        old = plugins / "ready" / "old"
        old.mkdir(parents=True)
        (old / "plugin.json").write_text(json.dumps({
            "name": "old",
            "module": "jarvis_news",
            "install": "handler",
            "stack_order": 5,
            "summary": "an old one.",
            "replaces_patch": "not-a-patch-any-more.patch",
        }), encoding="utf-8")
        data = with_plugins(gen, plugins, gen.build)
        check("catalogue: a stale patch mirror is REPORTED (not silently kept)",
              [u for u in data["unaccounted"] if u.get("folder") == "old"],
              str(data["unaccounted"]))
        removed = with_plugins(gen, plugins, lambda: gen.prune_ready(data))
        check("catalogue: write mode prunes a stale patch mirror",
              removed == ["old"] and not old.exists(), f"removed={removed}")


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
