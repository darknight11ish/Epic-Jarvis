"""test_reconcile_live_backend.py - the reusable deploy tool's own contract, proved hermetically.

    python3 test_reconcile_live_backend.py

WHAT THIS SUITE HOLDS

`tools/reconcile_live_backend.py` deploys the repository's backend onto the owner's live
folder. It is a sharp tool, so the tests are about the decisions it makes, never about the
real PC:

  1. the authoritative `$SHIPPED` / `$PATCHES` lists parse out of
     `scripts/apply-patches.ps1`, `rebuilt/<name>` flattens to the live base name, and a
     duplicate, `..` or base-folder entry is refused;
  2. the HUD-delta decision: a patch whose distinctive lines are present is
     ALREADY_PRESENT; one that is absent but has an anchor rule is inserted at exactly
     the configured anchor; an absent patch with no rule, or a missing/ambiguous anchor,
     is refused LOUDLY and nothing is staged;
  3. `py_compile` rehearsal stops a broken staged file before any live file is touched;
  4. the shipped sync compares BYTES, writes only changed/missing files, writes the
     repository's bytes exactly (LF preserved), and backs every overwritten file into a
     timestamped `_jarvis-deploy-backup-tool-<stamp>/`;
  5. the pycache purge deletes `.pyc` and leaves anything else;
  6. ready plug-ins: present ones are skipped, missing ones are passed to
     `add-plugin.ps1` with the right arguments, and a failure is reported, not hidden;
  7. the probe harness: PASS / FAIL / SKIP per probe, expected failures exit non-zero,
     conditional probes skip honestly, and the token never appears in the output;
  8. a full dry run and a full apply on a temporary "PC" (fake git blobs, fake probes,
     fake add-plugin runner) are idempotent: the second apply changes nothing and all
     probes pass;
  9. the backup journal: it is printed BEFORE any live write, a mid-apply or plug-in
     failure is rolled back from it (old bytes restored, new files removed), a probe
     failure after a COMPLETE write keeps the files and names the backup/journal
     instead, and `rollback_backup`/`--rollback` restores a partial state from the
     journal - all on temporary folders.

NOTHING HERE TOUCHES THE REAL LIVE FOLDER. Every path is under a temporary directory; the
only real repository files read are `scripts/apply-patches.ps1`, the two patches the
deploy uses and the published base HUD `jarvis-backend/jarvis_hud.py` (the literal
route delta's bytes are compared with it), for the parser/extraction tests (read-only).
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import sys
import tempfile
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import reconcile_live_backend as R  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def tmpdir(prefix="reconcile-test-"):
    return Path(tempfile.mkdtemp(prefix=prefix))


def write(path: Path, text: str = "", *, encoding="utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)
    return path


MINI_HUD = '''"""a live HUD stand-in"""


def _install(Handler):
    try:
        import jarvis_presets
        print(jarvis_presets.install(Handler))
    except Exception as exc:
        print(f"  presets    NOT ON ({type(exc).__name__})")
    # plugin-loader.patch (this branch).
    try:
        import jarvis_plugins
        print(jarvis_plugins.install(Handler))
    except Exception as exc:
        print(f"  plugins    NOT ON ({type(exc).__name__})")
    # Before the main socket, so the banner lists every address together.
    return True


def do_POST(self):
    route = ""
    if True:
        if route == "/api/memory/decide":
            return None
'''


# The literal HUD deltas' fixture pieces are in every fixture, without the
# fixes themselves: the same shape the real live HUD has (the pre-cache
# `/api/status` route probes upstream inline, the old reasoning relay, and the
# anchors the cache/start blocks go in front of). The literal deltas are only
# planned when the caller asks for them (plan_deltas(literals=True)), which
# main() does.
MINI_HUD += (
    "\n\n"
    "def do_GET(self):\n"
    "    path = \"\"\n"
    "    if True:\n"
    + "\n".join(R._delta_lines(R.STATUS_ROUTE_OLD_FILE)) + "\n\n"
    + R.STATUS_CACHE_ANCHOR + "\n\n"
    "def _relay():\n"
    "    if True:\n"
    "        if True:\n"
    "            if True:\n"
    "                if True:\n"
    + "\n".join(R._delta_lines(R.REASONING_OLD_FILE)) + "\n"
    "                    except (BrokenPipeError, ConnectionResetError, TimeoutError, socket.timeout):\n"
    "                        return\n\n"
    "def main():\n"
    "    print('hud')\n"
    + R.STATUS_START_ANCHOR + "\n"
)

# D12's fixture piece: the live file's own `_http_json`/`_reachable` pair, which
# no earlier delta has touched, so the loopback literal delta is planned against
# exactly what the owner's live HUD holds (the pre-#752 text: no helpers, no
# CONNECT pre-check). Added to every fixture for the same reason as the pieces
# above - the literal entries are only planned when literals=True.
MINI_HUD += (
    "\n\n"
    + "\n".join(R._delta_lines(R.LOOPBACK_OLD_FILE)) + "\n"
)

# PWA Slice 3a (2026-10-23): the two anchors its literal deltas insert in
# front of, present in every fixture exactly as the real live HUD has them,
# so a full-table plan can carry the static whitelist too. The fixture has
# none of that code itself - a plan has to insert both blocks.
MINI_HUD += (
    "\n\n"
    "class Handler(BaseHTTPRequestHandler):\n"
    "    def do_GET(self):\n"
    "        path = \"\"\n"
    "        if path in (\"/\", \"/index.html\"):\n"
    "            return None\n"
    "        return None\n"
)


def make_live(root: Path, *, with_deltas=False, app_control_section=False) -> Path:
    live = root / "live"
    live.mkdir(parents=True, exist_ok=True)
    hud = MINI_HUD
    if with_deltas:
        hud = R.insert_before_anchor(hud, ["        # app-control (test)", '        if route in ("/api/app-control/run",):', "            pass"],
                                     R.APP_CONTROL_ANCHOR, where="fixture")
        hud = R.insert_before_anchor(hud, ["    # setup.patch (test)", "    # /api/setup"],
                                     R.PLUGIN_LOADER_MARKER, where="fixture")
    write(live / "jarvis_hud.py", hud)
    # The gate gets the same kind of stand-in the HUD does: a COMPILABLE mini
    # module carrying the OLD blocks review ruling 8.2's guard deltas replace
    # (see MINI_GATE below). Without it, every test that plans the whole
    # DELTA_TABLE with literals=True would (rightly) be refused for a gate file
    # that cannot hold the guard change - a fixture gap, not a deploy finding.
    write(live / "jarvis_gate.py", MINI_GATE)
    for name in ("jarvis_extract.py", "jarvis_models.py", "jarvis_skills.py"):
        write(live / name, "# a live patched base file\n")
    write(live / "_jarvis-state.json", json.dumps({"patchList": [
        "rebuilt-patches/demo-old.patch"]}))
    toml = "[tools]\nenabled = []\n"
    if app_control_section:
        toml += "\n[app_control]\nenabled = false\n"
    write(live / "jarvis-framework.toml", toml)
    return live


def patch_text(name: str) -> bytes:
    return (REPO / "backend" / name).read_bytes()


def fake_show(repo, ref, repo_path):
    base = Path(repo_path).name
    if base in ("app-control.patch", "setup.patch"):
        return patch_text(base)
    blobs = {
        "jarvis_agent.py": b'"""agent"""\nVALUE = 2\n',
        "jarvis_compute.py": b'"""compute"""\nVALUE = 2\n',
        "jarvis_hud.html": b"<html>same</html>\n",
        "demo-unknown.patch": b"",
    }
    if repo_path in blobs:
        return blobs[repo_path]
    if base in blobs:
        return blobs[base]
    return b""


# --------------------------------------------------------------------------
#   1. the authoritative lists
# --------------------------------------------------------------------------

def t_the_lists_parse_from_apply_patches():
    script = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    shipped = R.parse_powershell_list(script, "SHIPPED")
    patches = R.parse_powershell_list(script, "PATCHES")
    check("$SHIPPED parses to many entries", len(shipped) >= 200, len(shipped))
    check("$PATCHES parses to many entries", len(patches) >= 100, len(patches))
    check("the shipped list carries a plain module", "jarvis_agent.py" in shipped)
    check("the shipped list carries a rebuilt module under rebuilt/",
          "rebuilt/jarvis_compute.py" in shipped)
    check("the shipped list carries the one non-Python beside file",
          "jarvis_hud.html" in shipped)
    check("the patch list ends with the loader, as the stack does",
          patches[-1] == "plugin-loader.patch", patches[-3:])
    check("the two deploy patches this tool knows are in the stack",
          "app-control.patch" in patches and "setup.patch" in patches)
    flat = R.flatten_shipped(shipped)
    names = [live for _repo, live in flat]
    check("flattening rebuilt/ gives the live base name",
          "jarvis_compute.py" in names and "rebuilt/jarvis_compute.py" not in names)
    check("flattening leaves the beside file alone", "jarvis_hud.html" in names)


def t_the_list_parser_refuses_rather_than_reading_nothing():
    for text, why in (
            ("no lists here", "no such block"),
            ("$SHIPPED = @(\n   'a.py'\n", "not closed"),
            ("$SHIPPED = @(\n)\n", "empty")):
        refused = ""
        try:
            R.parse_powershell_list(text, "SHIPPED")
        except R.Refused as exc:
            refused = str(exc)
        check(f"the parser refuses a bad list ({why})", bool(refused), refused)
    bad = [("a.py", "a.py", "duplicate"), ("rebuilt/x.py", "x.py", None)]
    try:
        R.flatten_shipped(["x.py", "rebuilt/x.py"])
    except R.Refused as exc:
        check("flattening refuses a duplicate live name", "twice" in str(exc), str(exc))
    for entry, needle in (("../evil.py", "safe relative"), ("C:/Windows/x.py", "safe relative"),
                          ("jarvis-backend/jarvis_hud.py", "never be deployed")):
        refused = ""
        try:
            R.flatten_shipped([entry])
        except R.Refused as exc:
            refused = str(exc)
        check(f"flattening refuses {entry!r}", needle in refused, refused)


# --------------------------------------------------------------------------
#   2. patches and the HUD-delta decision
# --------------------------------------------------------------------------

def t_a_patch_parses_into_per_file_added_lines():
    demo = ("--- a/jarvis_hud.py\n+++ b/jarvis_hud.py\n@@ -1,2 +1,4 @@\n"
            " context\n+        route = \"/api/demo/run\"\n+        return route\n"
            "--- a/jarvis_gate.py\n+++ b/jarvis_gate.py\n@@ -5,0 +6,1 @@\n"
            "+        \"demo\": \"ask\",\n")
    parsed = R.parse_patch_files(demo)
    check("two file sections are kept apart", set(parsed) == {"jarvis_hud.py",
                                                              "jarvis_gate.py"}, parsed)
    check("only added body lines are collected",
          parsed["jarvis_hud.py"]["added"] == ['        route = "/api/demo/run"',
                                               "        return route"],
          parsed["jarvis_hud.py"])
    real = patch_text("app-control.patch").decode("utf-8")
    hud = R.parse_patch_files(real)["jarvis_hud.py"]["added"]
    check("the real app-control patch's added lines name its routes",
          any("/api/app-control/run" in line for line in hud))
    setup = R.parse_patch_files(patch_text("setup.patch").decode("utf-8"))["jarvis_hud.py"]
    check("the real setup patch's added lines call jarvis_setup.install",
          any("jarvis_setup.install(" in line for line in setup["added"]))


def t_presence_is_decided_from_distinctive_lines():
    probes_ok = MINI_HUD + '        if route in ("/api/app-control/run",\n"                    "/api/app-control/step"):\n'
    check("all table probes present means ALREADY_PRESENT",
          R.patch_present("app-control.patch", "jarvis_hud.py",
                          ['        if route in ("/api/app-control/run", "/api/app-control/step",'],
                          probes_ok))
    half = MINI_HUD + '        if route in ("/api/app-control/run",\n'
    check("half a block is NOT present (the table needs every probe)",
          R.patch_present("app-control.patch", "jarvis_hud.py",
                          ['        if route in ("/api/app-control/run", "/api/app-control/step",'],
                          half) is False)
    generic = ["        # demo.patch (test)", "        marker_line = 1",
               "        another_line = 2"]
    check("a generic patch is present when any distinctive line is",
          R.patch_present("demo.patch", "jarvis_hud.py", generic,
                          "# x\nmarker_line = 1\n", table={}))
    check("... and absent when none is",
          R.patch_present("demo.patch", "jarvis_hud.py", generic,
                          "# x\nnothing here\n", table={}) is False)
    check("no distinctive lines falls back to the live state file",
          R.patch_present("demo-old.patch", "jarvis_hud.py", ["+", ""], "text",
                          table={}, state_patches=["rebuilt-patches/demo-old.patch"]))
    check("lines rewritten by later patches fall back to the state file too",
          R.patch_present("briefing.patch", "jarvis_gate.py", generic, "text",
                          table={}, state_patches=["briefing.patch"]))


def t_insertion_uses_its_anchor_and_refuses_a_bad_one():
    text = "first = 1\nANCHOR LINE\nlast = 2\n"
    out = R.insert_before_anchor(text, ["# inserted", "value = 3"], "ANCHOR LINE")
    check("the block lands immediately before the anchor",
          out.index("# inserted") < out.index("ANCHOR LINE") and "first = 1" in out, out)
    try:
        compile(out.replace("ANCHOR LINE", "ANCHOR_VALUE = 1"), "<test>", "exec")
        compiled = True
    except SyntaxError:
        compiled = False
    check("the inserted result compiles as Python", compiled)
    for bad, needle in ((text.replace("ANCHOR LINE", "x"), "appears 0 time"),
                        (text + "ANCHOR LINE\n", "appears 2 time")):
        refused = ""
        try:
            R.insert_before_anchor(bad, ["x = 1"], "ANCHOR LINE")
        except R.Refused as exc:
            refused = str(exc)
        check(f"a bad anchor is refused loudly ({needle})", needle in refused, refused)


def t_deltas_are_planned_and_refused_hermetically():
    root = tmpdir()
    try:
        live = make_live(root)
        patches = ["app-control.patch", "setup.patch"]
        deltas, staged, refusals = R.plan_deltas(live, patches, show=fake_show,
                                                 repo=REPO, state_patches=[])
        check("both absent HUD deltas are planned", refusals == [] and len(staged) == 1,
              (refusals, sorted(staged)))
        text = staged.get("jarvis_hud.py", "")
        check("the app-control route block is inside the HUD text",
              "/api/app-control/run" in text)
        check("the setup block is inside the HUD text", "/api/setup" in text)
        check("setup's block sits before the plugin-loader marker",
              text.index("/api/setup") < text.index(R.PLUGIN_LOADER_MARKER))
        check("py_compile accepts the staged HUD", R.rehearse(staged) == [],
              R.rehearse(staged))
        write(live / "jarvis_hud.py", text)          # pretend the deploy applied it
        again, staged2, refusals2 = R.plan_deltas(live, patches, show=fake_show,
                                                  repo=REPO, state_patches=[])
        check("a second plan sees both as ALREADY_PRESENT",
              refusals2 == [] and not staged2
              and all(d.status == "already" for d in again), (again, staged2))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_an_unknown_delta_is_refused_before_writing():
    root = tmpdir()
    try:
        live = make_live(root)
        unknown = ("--- a/jarvis_hud.py\n+++ b/jarvis_hud.py\n@@ -1,0 +1,1 @@\n"
                   "+        future_route = \"/api/future\"\n")
        show = lambda repo, ref, path: unknown.encode()          # noqa: E731
        before = (live / "jarvis_hud.py").read_bytes()
        deltas, staged, refusals = R.plan_deltas(live, ["future.patch"], show=show,
                                                 repo=REPO, state_patches=[])
        check("an absent patch with no anchor rule is refused",
              bool(refusals) and "no insertion rule" in refusals[0], refusals)
        check("... naming the patch and the file",
              "future.patch" in refusals[0] and "jarvis_hud.py" in refusals[0], refusals)
        check("... and nothing is staged", staged == {}, staged)
        check("... and the live file is untouched", (live / "jarvis_hud.py").read_bytes() == before)
        # A known patch with a missing anchor is refused too.
        broken = R.parse_patch_files(unknown)
        table = {"future.patch": {"jarvis_hud.py": {"probes": ("future_route",),
                                                    "anchor": "NOT IN THIS FILE"}}}
        _d, staged2, refusals2 = R.plan_deltas(live, ["future.patch"], show=show,
                                               repo=REPO, table=table, state_patches=[])
        check("a known patch with a missing anchor is refused loudly",
              bool(refusals2) and "appears 0 time" in refusals2[0], refusals2)
        check("... and still nothing is staged", staged2 == {}, staged2)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_rehearsal_stops_a_broken_staged_file():
    check("a good staged file rehearses", R.rehearse({"x.py": "value = 1\n"}) == [])
    errors = R.rehearse({"bad.py": "def broken(:\n"})
    check("a syntax error is reported and names the file",
          len(errors) == 1 and "bad.py" in errors[0], errors)


# --------------------------------------------------------------------------
#   3. shipped sync, bytes, backups
# --------------------------------------------------------------------------

def t_shipped_sync_compares_bytes_and_preserves_lf():
    root = tmpdir()
    try:
        live = root / "live"
        live.mkdir()
        (live / "same.py").write_bytes(b"same\n")
        (live / "old.py").write_bytes(b"old\r\ncontent\r\n")
        show = {"same.py": b"same\n", "old.py": b"new\ncontent\n",
                "new.py": b"brand-new\n"}

        def fake(repo, ref, repo_path):
            return show[Path(repo_path).name]

        shipped = ["same.py", "old.py", "rebuilt/new.py"]
        actions = R.plan_shipped(REPO, "origin/main", live, shipped, show=fake)
        status = {a.live_name: a.status for a in actions}
        check("same bytes are unchanged", status["same.py"] == "unchanged", status)
        check("different bytes are an update", status["old.py"] == "update", status)
        check("a missing file is an add", status["new.py"] == "add", status)
        backup = R.Backup(live, stamp="test")
        written = R.apply_shipped(actions, live, backup)
        check("only changed/missing files are written",
              sorted(written) == ["new.py", "old.py"], written)
        check("the update is the repository's bytes exactly (LF kept)",
              (live / "old.py").read_bytes() == b"new\ncontent\n",
              (live / "old.py").read_bytes())
        check("the add is exact", (live / "new.py").read_bytes() == b"brand-new\n")
        check("only the overwritten file was backed up",
              backup.saved == ["old.py"], backup.saved)
        check("the backup keeps the OLD bytes",
              (backup.root / "old.py").read_bytes() == b"old\r\ncontent\r\n")
        check("the backup folder carries the tool's name and stamp",
              backup.root.name == "_jarvis-deploy-backup-tool-test", backup.root.name)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_dry_run_plans_without_writing_or_backing_up():
    root = tmpdir()
    try:
        live = root / "live"
        live.mkdir()
        (live / "old.py").write_bytes(b"old\n")
        action = R.ShippedAction("old.py", "old.py", "update", b"new\n")
        backup = R.Backup(live, stamp="dry")
        written = R.apply_shipped([action], live, backup, write=False)
        check("the dry run lists the file it would write", written == ["old.py"])
        check("the dry run leaves the live file alone", (live / "old.py").read_bytes() == b"old\n")
        check("the dry run creates no backup folder", not backup.root.exists())
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_deltas_apply_with_backup():
    root = tmpdir()
    try:
        live = make_live(root)
        before = (live / "jarvis_hud.py").read_bytes()
        staged = {"jarvis_hud.py": MINI_HUD + "# staged\n"}
        backup = R.Backup(live, stamp="delta")
        written = R.apply_deltas(staged, live, backup)
        check("the staged HUD is the file written", written == ["jarvis_hud.py"])
        check("the live HUD is the staged text", (live / "jarvis_hud.py").read_text(
            encoding="utf-8").endswith("# staged\n"))
        check("the old HUD bytes are in the backup",
              (backup.root / "jarvis_hud.py").read_bytes() == before)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------
#   4. pycache, plug-ins
# --------------------------------------------------------------------------

def t_pycache_purge_removes_only_bytecode():
    root = tmpdir()
    try:
        live = root / "live"
        (live / "__pycache__").mkdir(parents=True)
        (live / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"pyc")
        (live / "__pycache__" / "notes.txt").write_text("keep", encoding="utf-8")
        planned = R.plan_pycache(live)
        check("the plan names the .pyc file", [p.name for p in planned] == ["a.cpython-312.pyc"],
              planned)
        deleted = R.purge_pycache(live)
        check("the purge deletes it", deleted == ["a.cpython-312.pyc"], deleted)
        check("the non-bytecode file is left alone",
              (live / "__pycache__" / "notes.txt").is_file())
        check("a second purge finds nothing", R.purge_pycache(live) == [])
        check("a live folder with no __pycache__ is fine", R.plan_pycache(root) == [])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_ready_plugins_plan_and_invocation():
    root = tmpdir()
    try:
        repo = root / "repo"
        live = repo / "live"
        write(repo / "scripts" / "add-plugin.ps1", "# stub\n")
        for name, module in (("one", "jarvis_one"), ("two", "jarvis_two")):
            write(repo / "plugins" / "ready" / name / "plugin.json",
                  json.dumps({"name": name, "module": module}))
        write(repo / "plugins" / "ready" / "broken" / "plugin.json", "{not json")
        (live / "jarvis_plugins" / "one").mkdir(parents=True)
        write(live / "jarvis_hud.py", "        jarvis_one.install(Handler)\n")
        missing, present, broken, wired = R.plan_plugins(live, repo)
        check("a present plug-in is skipped", present == ["one"], present)
        check("a missing plug-in is planned", missing == ["two"], missing)
        check("a module the HUD already installs is not added twice",
              wired == [] and missing == ["two"], wired)
        check("a broken manifest is reported", any("broken" in b for b in broken), broken)
        calls = []

        def runner(argv, cwd=None):
            calls.append(argv)
            return SimpleNamespace(returncode=0, stdout="  added     two\n", stderr="")

        with mock.patch.object(R, "_powershell", return_value="C:/fake/powershell.exe"):
            ok, why = R.add_plugin(repo, live, "two", runner=runner)
        check("the plug-in is added by running add-plugin.ps1", ok and "added" in why, why)
        joined = " ".join(calls[0]) if calls else ""
        check("... non-interactively, with the backend path and the name",
              "-NonInteractive" in joined and "-BackendPath" in joined
              and str(live) in joined and "-Name two" in joined, joined)
        with mock.patch.object(R, "_powershell", return_value=""):
            ok2, why2 = R.add_plugin(repo, live, "two", runner=runner)
        check("no PowerShell is a reported failure, not a crash",
              ok2 is False and "PowerShell" in why2, why2)

        def failing(argv, cwd=None):
            return SimpleNamespace(returncode=1, stdout="", stderr="boom")

        with mock.patch.object(R, "_powershell", return_value="C:/fake/powershell.exe"):
            ok3, why3 = R.add_plugin(repo, live, "two", runner=failing)
        check("a failing add-plugin run is reported as a failure",
              ok3 is False, (ok3, why3))
        missing, present, broken, wired = R.plan_plugins(live, repo)
        check("planning does not invoke anything on its own", calls and len(calls) == 1)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_hud_wired_ready_plugin_is_not_added_again():
    root = tmpdir()
    try:
        repo = root / "repo"
        live = repo / "live"
        write(repo / "scripts" / "add-plugin.ps1", "# stub\n")
        write(repo / "plugins" / "ready" / "wired" / "plugin.json",
              json.dumps({"name": "wired", "module": "jarvis_wired"}))
        write(repo / "plugins" / "ready" / "fresh" / "plugin.json",
              json.dumps({"name": "fresh", "module": "jarvis_fresh"}))
        write(live / "jarvis_hud.py", "    print(jarvis_wired.install(Handler))\n")
        missing, present, broken, wired = R.plan_plugins(live, repo)
        check("a ready plug-in the HUD already installs is SKIPped",
              wired == ["wired"] and "wired" not in missing, (missing, wired))
        check("a genuinely unwired ready plug-in is still planned",
              missing == ["fresh"], missing)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------
#   5. the probe harness
# --------------------------------------------------------------------------

TOKEN = "sentinel-token-that-must-not-print"


def make_probe_live(root: Path, *, media=False, app_control=False,
                    voice_ok=True) -> Path:
    live = root / "live"
    write(live / "jarvis_hud.py",
          'HUD_PORT = int(os.environ.get("JARVIS_HUD_PORT", "4719"))\n')
    write(live / "jarvis_token_store.py", "# probe fixture\n")
    toml = "[tools]\n"
    if app_control:
        toml += "\n[app_control]\nenabled = false\n"
    write(live / "jarvis-framework.toml", toml)
    if media:
        (live / "jarvis_plugins" / "media-index").mkdir(parents=True)
    return live


def t_probes_pass_fail_and_skip_honestly():
    root = tmpdir()
    try:
        live = make_probe_live(root, media=True, app_control=False, voice_ok=True)
        seen = []

        def client(url, method="GET", body=None, token=""):
            seen.append((url, method, token))
            if url.endswith("/api/setup"):
                return 200, {"ok": True}
            if url.endswith("/api/media-index"):
                return 200, {"ok": True}
            if url.endswith("/api/app-control/run"):
                return 409, {"error": "switched off"}
            if url.endswith("/api/voice/status"):
                return 200, {"gate": {"training": {"clear": True}}}
            return 404, {}

        lines = []
        failures = R.run_probes(live, "http://127.0.0.1:9", client=client,
                                token_reader=lambda _live: TOKEN,
                                out=lines.append)
        text = "\n".join(lines)
        check("every expected probe passed", failures == 0, (failures, text))
        check("the token is never printed", TOKEN not in text, text)
        check("the token was sent on every probe",
              all(tok == TOKEN for _u, _m, tok in seen) and len(seen) == 4, seen)
        check("the app-control probe used POST", any(
            m == "POST" and u.endswith("/api/app-control/run") for u, m, _t in seen))
        check("the media-index probe ran because the plug-in is present",
              any(u.endswith("/api/media-index") for u, _m, _t in seen))

        lines2 = []
        failures2 = R.run_probes(live, "http://127.0.0.1:9",
                                 client=lambda *a, **k: (500, {}),
                                 token_reader=lambda _live: TOKEN,
                                 out=lines2.append)
        check("a 500 on an expected probe is a failure", failures2 >= 2, lines2)
        check("... and prints FAIL lines", any(str(l).startswith("FAIL") for l in lines2))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_probes_skip_what_cannot_be_expected():
    root = tmpdir()
    try:
        live = make_probe_live(root, media=False, app_control=True)
        lines = []
        failures = R.run_probes(live, "http://127.0.0.1:9",
                                client=lambda *a, **k: (200, {"gate": {"training": {}}}),
                                token_reader=lambda _live: TOKEN,
                                out=lines.append)
        text = "\n".join(lines)
        check("no media-index plug-in means that probe SKIPs",
              "SKIP  media-index" in text, text)
        check("an [app_control] section means the 409-when-off probe SKIPs",
              "SKIP  app-control" in text, text)
        check("... and no failure is invented for a skip", failures == 0, failures)

        lines2 = []
        failures2 = R.run_probes(live, "http://127.0.0.1:9",
                                 client=lambda *a, **k: (200, {"gate": {}}),
                                 token_reader=lambda _live: TOKEN,
                                 out=lines2.append)
        check("voice status without gate.training is a FAIL", failures2 == 1, lines2)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_missing_token_fails_the_probes_without_printing_one():
    root = tmpdir()
    try:
        live = make_probe_live(root)
        lines = []
        failures = R.run_probes(
            live, "http://127.0.0.1:9", client=lambda *a, **k: (200, {}),
            token_reader=lambda _live: (_ for _ in ()).throw(
                R.ProbeError("no token here")),
            out=lines.append)
        check("a token problem is one FAIL and a non-zero result", failures == 1, lines)
        check("the failure names the problem, not a value",
              "no token here" in "\n".join(lines), lines)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------
#   6. end to end on a temporary "PC", and idempotence
# --------------------------------------------------------------------------

def make_fixture_pc(root: Path):
    """A fake repository + live backend. Returns (repo, live, show)."""
    repo = root / "repo"
    write(repo / "scripts" / "apply-patches.ps1", """$SHIPPED = @(
    'jarvis_agent.py'
    'rebuilt/jarvis_compute.py'
    'jarvis_hud.html'
)
$PATCHES = @(
    'app-control.patch'
    'setup.patch'
)
""")
    write(repo / "scripts" / "add-plugin.ps1", "# stub\n")
    (repo / ".git").mkdir(parents=True)
    live = make_live(root)
    (live / "jarvis_agent.py").write_bytes(b'"""agent old"""\nVALUE = 1\n')
    (live / "jarvis_hud.html").write_bytes(b"<html>same</html>\n")
    return repo, live, fake_show


def run_fixture(repo: Path, live: Path, *, apply: bool, out_lines=None,
                probe_client=None, **kw):
    out = (out_lines.append if out_lines is not None else (lambda _m: None))

    def client(url, method="GET", body=None, token=""):
        if url.endswith("/api/setup"):
            return 200, {}
        if url.endswith("/api/app-control/run"):
            return 409, {"error": "off"}
        if url.endswith("/api/voice/status"):
            return 200, {"gate": {"training": {}}}
        return 404, {}

    client = probe_client or client

    return R.run_deploy(repo, live, apply=apply, ref="origin/main",
                        show=kw.pop("show", fake_show),
                        out=out, probe_client=client,
                        token_reader=lambda _live: TOKEN,
                        plugin_runner=lambda argv, cwd=None: SimpleNamespace(
                            returncode=0, stdout="added\n", stderr=""),
                        stamp="fixture", **kw)


def t_end_to_end_and_idempotent():
    root = tmpdir()
    try:
        repo, live, show = make_fixture_pc(root)
        before = {p.name: p.read_bytes() for p in live.iterdir() if p.is_file()}
        lines = []
        code = run_fixture(repo, live, apply=False, out_lines=lines)
        check("a dry run succeeds", code == 0, (code, lines[-5:]))
        after = {p.name: p.read_bytes() for p in live.iterdir() if p.is_file()}
        check("a dry run writes nothing", after == before)
        check("... and creates no backup folder",
              not any(p.name.startswith("_jarvis-deploy-backup-tool-") for p in live.iterdir()))
        check("... and does not probe", not any("ROUTE PROBES" in l for l in lines), lines[-5:])

        lines2 = []
        code2 = run_fixture(repo, live, apply=True, out_lines=lines2)
        text2 = "\n".join(lines2)
        check("the apply succeeds", code2 == 0, (code2, lines2[-8:]))
        check("the shipped module was updated to the repository bytes",
              (live / "jarvis_agent.py").read_bytes() == b'"""agent"""\nVALUE = 2\n')
        check("the missing rebuilt module was added",
              (live / "jarvis_compute.py").read_bytes() == b'"""compute"""\nVALUE = 2\n')
        check("the HUD gained app-control", "/api/app-control/run" in
              (live / "jarvis_hud.py").read_text(encoding="utf-8"))
        check("the HUD gained setup before the loader marker",
              "/api/setup" in (live / "jarvis_hud.py").read_text(encoding="utf-8"))
        backups = [p for p in live.iterdir() if p.name.startswith(
            "_jarvis-deploy-backup-tool-fixture")]
        check("a backup folder was made with the old files",
              len(backups) == 1 and (backups[0] / "jarvis_agent.py").is_file(), backups)
        check("the probes ran and passed", "RESULT: PASS" in text2, text2[-6:])

        lines3 = []
        code3 = run_fixture(repo, live, apply=True, out_lines=lines3)
        text3 = "\n".join(lines3)
        check("the second apply is idempotent", code3 == 0, (code3, lines3[-8:]))
        check("... it changes nothing", "no file changed (already current)" in text3, text3[-6:])
        check("... all probes still pass", "RESULT: PASS" in text3, text3[-6:])
        check("... no second backup folder is created",
              len([p for p in live.iterdir() if p.name.startswith(
                  "_jarvis-deploy-backup-tool-fixture")]) == 1)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_cli_is_dry_run_by_default_and_validates_paths():
    root = tmpdir()
    try:
        repo, live, show = make_fixture_pc(root)
        # main() has no injection points, so only its argument handling is exercised here;
        # the deploy seam above is the real end-to-end proof.
        code = R.main(["--backend-path", str(root / "no-such-folder")])
        check("a nonexistent backend path is refused (exit 2)", code == 2, code)
        code2 = R.main(["--backend-path", str(live), "--apply", "--dry-run"])
        check("--apply and --dry-run together are refused (exit 2)", code2 == 2, code2)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_traces_retention_is_recorded_blocked_not_guessed():
    """F10 / Q2 (2026-10-20): traces.db retention is recorded as BLOCKED.

    The live HUD was read read-only and has no traces.db writer, schema or anchor.
    A retention cap must not be guessed into a database this program does not own,
    so the decision lives in BLOCKED_DELTAS and is printed - never staged."""
    entry = R.BLOCKED_DELTAS.get("traces-retention")
    check("traces-retention is recorded in BLOCKED_DELTAS", isinstance(entry, dict), entry)
    check("... and is NOT in DELTA_TABLE, so no deploy ever tries to insert it",
          "traces-retention" not in R.DELTA_TABLE, sorted(R.DELTA_TABLE))
    evidence = " ".join([str(entry.get("why") or "")]
                        + [str(x) for x in (entry.get("evidence") or ())])
    for probe in ("traces.db", "jarvis_hud.py", "no traces.db writer",
                  "6238-6265", "snapshot", "no delete trigger"):
        check(f"... the evidence names {probe!r}", probe in evidence, evidence[:200])
    lines = R.blocked_delta_lines()
    check("... the dry-run summary will print it as blocked, not as an insert",
          len(lines) == 1 and lines[0].startswith("traces-retention -> jarvis_hud.py:"),
          lines)


def t_a_fake_traces_delta_uses_the_anchored_mechanism_without_writing():
    """What the tool WOULD do if the live HUD ever grew a safe anchor.

    A test-local delta (not in DELTA_TABLE) is fed the same fake HUD text and a
    synthetic patch: the shared ALREADY_PRESENT probe, the anchored insert, a
    missing-anchor refusal and a dry run that writes nothing are all exercised.
    The live files stay untouched; this is the mechanism the blocked entry cannot
    use today."""
    root = tmpdir()
    try:
        live = make_live(root)
        anchor = 'FACTS_FILE = CONFIG_DIR / "memory_facts.jsonl"'
        hud = ('"""a fake live HUD for the blocked delta"""\n\n'
               'CONFIG_DIR = 1\n' + anchor + '\n')
        write(live / "jarvis_hud.py", hud)
        block = ("# F10 traces.db retention (test block)",
                 "_TRACES_KEEP_ROWS = 2000",
                 "def _prune_traces_db():",
                 "    pass",
                 "_prune_traces_db()")
        patch = ("--- a/jarvis_hud.py\n+++ b/jarvis_hud.py\n@@\n"
                 + "".join("+" + line + "\n" for line in block))
        table = {"traces-retention": {"jarvis_hud.py": {
            "probes": tuple(block), "anchor": anchor}}}
        show = lambda repo, ref, path: patch                  # noqa: E731

        deltas, staged, refusals = R.plan_deltas(
            live, ["traces-retention"], show=show, repo=live, table=table)
        check("a fake traces delta with an anchor is PLANNED as an insert",
              refusals == [] and any(d.status == "insert" for d in deltas),
              (deltas, refusals))
        check("... the staged HUD contains the block before the anchor",
              anchor in staged.get("jarvis_hud.py", "")
              and "_prune_traces_db()" in staged["jarvis_hud.py"])
        check("... planning wrote NOTHING to the live file",
              (live / "jarvis_hud.py").read_text(encoding="utf-8") == hud)

        backup = R.Backup(live, stamp="traces-dry")
        would = R.apply_deltas(staged, live, backup, write=False)
        check("... a dry-run apply lists the file and writes nothing",
              would == ["jarvis_hud.py"]
              and (live / "jarvis_hud.py").read_text(encoding="utf-8") == hud
              and not backup.saved, (would, backup.saved))

        write(live / "jarvis_hud.py", staged["jarvis_hud.py"])
        deltas2, staged2, refusals2 = R.plan_deltas(
            live, ["traces-retention"], show=show, repo=live, table=table)
        check("... once present, the same probes say ALREADY_PRESENT",
              refusals2 == [] and [d.status for d in deltas2] == ["already"]
              and staged2 == {}, (deltas2, staged2, refusals2))

        bad = hud.replace(anchor, "OTHER = 1")
        write(live / "jarvis_hud.py", bad)
        deltas3, staged3, refusals3 = R.plan_deltas(
            live, ["traces-retention"], show=show, repo=live, table=table)
        check("... and a missing anchor is REFUSED loudly, with nothing staged",
              bool(refusals3) and "appears 0 time" in refusals3[0] and staged3 == {},
              (refusals3, staged3))
        check("... the file stays exactly as it was",
              (live / "jarvis_hud.py").read_text(encoding="utf-8") == bad)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_two_2026_10_14_hud_fixes_are_literal_deltas():
    """DELTA_TABLE carries the two fixes no .patch owns (status cache, reasoning
    fallback). Mutation bite: with the old patch-only planner nothing is staged
    and this fails. The third literal delta (DEF-002's route) is proved by
    `t_the_api_status_route_delta_replaces_the_inline_route` below."""
    root = tmpdir()
    try:
        live = make_live(root)
        deltas, staged, refusals = R.plan_deltas(live, [], show=fake_show,
                                                 literals=True)
        by = {d.patch: d.status for d in deltas}
        check("both 2026-10-14 fixes are planned as literal inserts",
              refusals == [] and by.get("hud-status-cache.patch") == "insert"
              and by.get("hud-status-poll-start.patch") == "insert"
              and by.get("hud-reasoning-fallback.patch") == "insert",
              (deltas, refusals))
        text = staged.get("jarvis_hud.py", "")
        check("the status cache block is inserted before # Brain graph",
              "# /api/status answers from HERE" in text
              and text.index("# /api/status answers from HERE")
              < text.index("# Brain graph") and "_status_poller_daemon" in text, text[:200])
        check("the poller is started from main()",
              "\n    _status_start_poller()" in text)
        check("the reasoning wrapper replaces the old relay",
              "CloudAnswer" in text
              and "\n".join(R._delta_lines(R.REASONING_OLD_FILE)) not in text)
        check("the staged HUD still compiles", R.rehearse(staged) == [], R.rehearse(staged))
        backup = R.Backup(live, stamp="hud-fix")
        R.apply_deltas(staged, live, backup)
        again, staged2, refusals2 = R.plan_deltas(live, [], show=fake_show,
                                                  literals=True)
        statuses = {d.patch: d.status for d in again}
        check("a second plan sees both fixes ALREADY_PRESENT",
              refusals2 == [] and staged2 == {}
              and statuses.get("hud-status-cache.patch") == "already"
              and statuses.get("hud-reasoning-fallback.patch") == "already",
              (again, staged2, refusals2))
    finally:
        shutil.rmtree(root, ignore_errors=True)


#: The ten keys `/api/status` answered with, before and after the route rewrite.
#: A4 (2026-10-23) adds two more through the CHAINED delta below
#: (`STATUS_LATCH_KEYS`); they are kept apart because the route delta's own
#: old/new pair predates them and must still prove the ten.
STATUS_PAYLOAD_KEYS = ('"routing"', '"jarvis_injects_memory"', '"budget"',
                       '"jarvis"', '"ollama"', '"proxy"', '"models"', '"lanes"',
                       '"default_model"', '"tools"')

#: A4 (2026-10-23): the two read-only session-latch keys the chained delta adds.
STATUS_LATCH_KEYS = ('"taint_latched"', '"rush_latched"')


def _status_route_ast(source: str) -> str:
    """`ast.dump` of the one `if path == "/api/status":` statement in `source`, or "".

    STRUCTURAL, never textual: comments and reformatting cannot change it, and a
    docstring is an `ast.Constant` rather than a statement. This is the shape the
    no-source-pins rule asks for when two copies of a route must be compared."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
                and test.left.id == "path" and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "/api/status"):
            return ast.dump(node, include_attributes=False)
    return ""


def t_the_api_status_route_delta_replaces_the_inline_route():
    """DEF-002's route half (2026-10-20): the live `/api/status` route is the
    pre-cache one that probes upstream inline (measured 3094/3117 ms plain,
    3084/3097 ms with `?force=1`), so the base's cached route must REPLACE it.
    Bite: with no DELTA_TABLE entry the plan stages nothing and (a) fails; with
    the old block present twice the deploy must refuse, not guess."""
    root = tmpdir()
    try:
        old = "\n".join(R._delta_lines(R.STATUS_ROUTE_OLD_FILE))
        new = "\n".join(R._delta_lines(R.STATUS_ROUTE_NEW_FILE))
        # `.get` so a missing DELTA_TABLE entry FAILS (a) loudly instead of
        # raising KeyError: the bite must read as "not planned", not as a crash.
        table = {"hud-status-route.patch": R.DELTA_TABLE.get("hud-status-route.patch") or {}}
        base_source = (REPO / "jarvis-backend" / "jarvis_hud.py").read_text(encoding="utf-8")
        # The chain's last link (`status-latches-new.txt`) proves byte-for-byte
        # that the base's CURRENT route is the published text - see
        # `t_the_session_latch_delta_chains_after_the_status_route_delta`. Here
        # only the pre-A4 block's own shape is proved: it IS a /api/status route
        # (the base has since grown A4's read-only latch fields on top of it).
        check("the NEW block is structurally a /api/status route (the base's own "
              "route before A4's latch fields were chained on)",
              _status_route_ast(textwrap.dedent(new)) != ""
              and _status_route_ast(textwrap.dedent(new)) != _status_route_ast(base_source))
        check("the OLD block is the live inline-probing route (no cache, no force)",
              'jarvis_up = _reachable(f"{JARVIS_URL}/health")' in old
              and '_reachable(f"{OLLAMA_URL}/api/tags")' in old
              and '_reachable(f"{PROXY_URL}/health")' in old
              and "_STATUS_CACHE" not in old and "force" not in old)
        check("old and new are different routes, so the delta is really needed",
              old != new)
        check("the NEW block reads the cache and handles ?force=1",
              "from urllib.parse import parse_qs, urlparse" in new
              and "if force or not _STATUS_CACHE:" in new
              and "with _STATUS_LOCK:" in new
              and "upstream = dict(_STATUS_CACHE)" in new)
        check("old and new keep the same ten payload keys",
              all(k in old and k in new for k in STATUS_PAYLOAD_KEYS)
              and len(STATUS_PAYLOAD_KEYS) == 10)

        live = make_live(root)
        check("the fixture carries the OLD route block exactly once",
              MINI_HUD.count(old) == 1, MINI_HUD.count(old))

        # (a) the plan stages the replacement.
        deltas, staged, refusals = R.plan_deltas(live, [], show=fake_show,
                                                 table=table, literals=True)
        check("(a) the status-route delta is planned as a literal REPLACE",
              refusals == [] and [(d.patch, d.status) for d in deltas]
              == [("hud-status-route.patch", "insert")], (deltas, refusals))
        text = staged.get("jarvis_hud.py", "")
        check("(a) the staged HUD carries the NEW cached route", new in text, text[:200])
        check("(a) ... and none of the OLD inline route is left",
              old not in text
              and 'jarvis_up = _reachable(f"{JARVIS_URL}/health")' not in text)
        check("(a) ... and the staged HUD still compiles",
              R.rehearse(staged) == [], R.rehearse(staged))

        # (b) after apply the temp live file holds exactly the staged text - the
        # new route and none of the old inline probes, both proved on `text`.
        # Byte equality is the write contract; no source-text pin on a module.
        backup = R.Backup(live, stamp="status-route")
        written = R.apply_deltas(staged, live, backup)
        check("(b) the apply wrote exactly the staged text (new route, old probes gone)",
              written == ["jarvis_hud.py"] and backup.saved == ["jarvis_hud.py"]
              and (live / "jarvis_hud.py").read_bytes() == text.encode("utf-8"),
              (written, backup.saved))

        # (c) a second plan says already present and stages nothing.
        again, staged2, refusals2 = R.plan_deltas(live, [], show=fake_show,
                                                  table=table, literals=True)
        check("(c) a second plan says ALREADY_PRESENT (idempotent)",
              refusals2 == [] and staged2 == {}
              and [(d.patch, d.status) for d in again]
              == [("hud-status-route.patch", "already")], (again, staged2, refusals2))

        # (d) the old block twice is refused, never guessed at.
        write(live / "jarvis_hud.py", MINI_HUD + "\n\n" + old + "\n")
        _d3, staged3, refusals3 = R.plan_deltas(live, [], show=fake_show,
                                                table=table, literals=True)
        check("(d) a live file where the old route block appears twice is REFUSED",
              staged3 == {} and any("hud-status-route.patch" in r
                                    and "appears 2 time" in r for r in refusals3),
              (staged3, refusals3))

        # (e) an already-cached route never stages the delta.
        write(live / "jarvis_hud.py", MINI_HUD.replace(old, new))
        _d4, staged4, refusals4 = R.plan_deltas(live, [], show=fake_show,
                                                table=table, literals=True)
        check("(e) a live route that is already cached is never staged",
              refusals4 == [] and staged4 == {}
              and [d.status for d in _d4] == ["already"], (_d4, staged4, refusals4))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_session_latch_delta_chains_after_the_status_route_delta():
    """A4 (2026-10-23): the two persistent session safety latches, READ-ONLY, in
    `/api/status`. The live PC never gets `jarvis-backend/*` copied over it, so
    the change must ride the same literal-delta mechanism as the route itself -
    and it CHAINS: its OLD block is exactly the cached route the
    `hud-status-route` entry leaves behind (byte-identical to
    `status-route-new.txt`, proved here), and its NEW block is the published
    base's route with the two fields, byte for byte. Bite: without the entry the
    plan stages nothing and (a) fails; a live file carrying the OLD cached route
    twice is refused; a fresh (inline-route) live file gets BOTH changes, in
    order."""
    root = tmpdir()
    try:
        old = "\n".join(R._delta_lines(R.STATUS_LATCHES_OLD_FILE))
        new = "\n".join(R._delta_lines(R.STATUS_LATCHES_NEW_FILE))
        route_old = "\n".join(R._delta_lines(R.STATUS_ROUTE_OLD_FILE))
        route_new = "\n".join(R._delta_lines(R.STATUS_ROUTE_NEW_FILE))
        base_source = (REPO / "jarvis-backend" / "jarvis_hud.py").read_text(encoding="utf-8")
        table = {"hud-status-latches.patch":
                 R.DELTA_TABLE.get("hud-status-latches.patch") or {}}
        full_table = {
            "hud-status-route.patch": R.DELTA_TABLE.get("hud-status-route.patch") or {},
            "hud-status-latches.patch": table["hud-status-latches.patch"],
        }

        # ---- the delta's own bytes: chained, and the base's own route -------
        check("the latch delta's OLD block is exactly the cached route the route "
              "delta leaves behind (the chain cannot drift)",
              old != "" and old == route_new)
        check("... and the NEW block is the published base's route text, byte for byte",
              new != "" and base_source.count(new) == 1)
        check("the latch delta is ordered AFTER the status-route delta in DELTA_TABLE",
              list(R.DELTA_TABLE).index("hud-status-route.patch")
              < list(R.DELTA_TABLE).index("hud-status-latches.patch"))
        check("the NEW block is structurally the base HUD's own /api/status route",
              _status_route_ast(textwrap.dedent(new)) != ""
              and _status_route_ast(textwrap.dedent(new))
              == _status_route_ast(base_source))
        check("... and it carries the ten existing keys plus the two latch keys",
              all(k in new for k in STATUS_PAYLOAD_KEYS + STATUS_LATCH_KEYS)
              and len(STATUS_PAYLOAD_KEYS) == 10 and len(STATUS_LATCH_KEYS) == 2)
        check("... the fields are read from the two real latches, read-only",
              "jarvis_gate.taint_active()" in new
              and "jarvis_content_risk" in new and "rush_active()" in new)
        check("... a READ only: the route adds no clear/approve/decide call",
              all(word not in new for word in
                  ("clear_taint", "clear_rush", "confirm_auto", "decide_approval",
                   "latch_taint(", "latch_rush(", "/api/approve", "/api/deny")))

        # ---- (a) this PC: the cached route is already there -> one insert ----
        live = make_live(root / "pc")
        write(live / "jarvis_hud.py", MINI_HUD.replace(route_old, route_new))
        deltas, staged, refusals = R.plan_deltas(live, [], show=fake_show,
                                                 table=table, literals=True)
        check("(a) a live file that already has the cached route plans the latch "
              "delta as a literal REPLACE",
              refusals == [] and [(d.patch, d.status) for d in deltas]
              == [("hud-status-latches.patch", "insert")], (deltas, refusals))
        text = staged.get("jarvis_hud.py", "")
        check("(a) the staged HUD carries the latch keys and none of the old cached route",
              new in text and route_new not in text, text[:200])
        check("(a) ... and the staged HUD still compiles",
              R.rehearse(staged) == [], R.rehearse(staged))
        backup = R.Backup(live, stamp="status-latches")
        written = R.apply_deltas(staged, live, backup)
        check("(a) ... and the apply wrote exactly the staged text",
              written == ["jarvis_hud.py"]
              and (live / "jarvis_hud.py").read_bytes() == text.encode("utf-8"))
        again, staged2, refusals2 = R.plan_deltas(live, [], show=fake_show,
                                                  table=table, literals=True)
        check("(a) ... a second plan sees the latch delta ALREADY_PRESENT",
              refusals2 == [] and staged2 == {}
              and [d.status for d in again] == ["already"], (again, staged2, refusals2))

        # ---- (b) a fresh live folder: route delta first, then the latch -------
        live2 = make_live(root / "fresh")
        deltas2, staged2b, refusals2b = R.plan_deltas(live2, [], show=fake_show,
                                                      table=full_table, literals=True)
        check("(b) a fresh (inline-route) live folder gets BOTH changes in order",
              refusals2b == []
              and [(d.patch, d.status) for d in deltas2]
              == [("hud-status-route.patch", "insert"),
                  ("hud-status-latches.patch", "insert")], (deltas2, refusals2b))
        text2 = staged2b.get("jarvis_hud.py", "")
        check("(b) ... the staged HUD ends with the cached route AND the latch keys",
              new in text2 and route_new not in text2 and route_old not in text2,
              text2[:200])
        check("(b) ... and it still compiles", R.rehearse(staged2b) == [],
              R.rehearse(staged2b))
        R.apply_deltas(staged2b, live2, R.Backup(live2, stamp="chain"))
        _d2, staged2c, refusals2c = R.plan_deltas(live2, [], show=fake_show,
                                                  table=full_table, literals=True)
        check("(b) ... and a second plan sees both ALREADY_PRESENT",
              refusals2c == [] and staged2c == {}
              and [d.status for d in _d2] == ["already", "already"],
              (_d2, staged2c, refusals2c))

        # ---- (c) a half-applied live file is refused, never guessed ---------
        write(live2 / "jarvis_hud.py",
              MINI_HUD.replace(route_old, route_new) + "\n\n" + route_new + "\n")
        _d3, staged3, refusals3 = R.plan_deltas(live2, [], show=fake_show,
                                                table=table, literals=True)
        check("(c) a live file where the OLD cached route appears twice is REFUSED",
              staged3 == {} and any("hud-status-latches.patch" in r
                                    and "appears 2 time" in r for r in refusals3),
              (staged3, refusals3))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_loopback_connect_delta_ships_the_020_timeout():
    """D12 (2026-10-23): #752 added a 0.20 s loopback CONNECT cap to the
    published base HUD's `_http_json`/`_reachable`, but NO patch carries it and
    no DELTA_TABLE entry shipped it. So the owner's live `jarvis_hud.py` still
    holds the pre-#752 pair (no CONNECT pre-check: a dead local port burns the
    full 1.5 s HTTP timeout) - the fix existed on paper only. This literal
    REPLACE ships it, chained after A4.

    Each check bites: the NEW block is the published base's own text byte for
    byte; the OLD block is the live file's own pre-#752 pair (the base no longer
    holds it); the STAGED live text is EXECUTED against a fake socket and must
    pass 0.20 s as the CONNECT timeout and treat a dead port as down without the
    HTTP wait; a duplicated old block is refused; a second plan is idempotent;
    and the full chain (route -> latches -> loopback) stages in that order."""
    root = tmpdir()
    try:
        old = "\n".join(R._delta_lines(R.LOOPBACK_OLD_FILE))
        new = "\n".join(R._delta_lines(R.LOOPBACK_NEW_FILE))
        route_old = "\n".join(R._delta_lines(R.STATUS_ROUTE_OLD_FILE))
        route_new = "\n".join(R._delta_lines(R.STATUS_ROUTE_NEW_FILE))
        latches_new = "\n".join(R._delta_lines(R.STATUS_LATCHES_NEW_FILE))
        base_source = (REPO / "jarvis-backend" / "jarvis_hud.py").read_text(encoding="utf-8")
        table = {"hud-loopback-connect.patch":
                 R.DELTA_TABLE.get("hud-loopback-connect.patch") or {}}
        full_table = {
            "hud-status-route.patch": R.DELTA_TABLE.get("hud-status-route.patch") or {},
            "hud-status-latches.patch": R.DELTA_TABLE.get("hud-status-latches.patch") or {},
            "hud-loopback-connect.patch": table["hud-loopback-connect.patch"],
        }

        # ---- the delta's bytes, and where it sits in the chain --------------
        check("the loopback delta is a literal REPLACE in DELTA_TABLE",
              bool(table["hud-loopback-connect.patch"].get("jarvis_hud.py", {})
                   .get("replace_file"))
              and bool(table["hud-loopback-connect.patch"].get("jarvis_hud.py", {})
                       .get("file")))
        check("... its NEW block is the published base's own text, byte for byte",
              new != "" and base_source.count(new) == 1)
        check("... its OLD block is the pre-#752 pair the base no longer holds",
              old != "" and old != new and old not in base_source)
        check("... and it is ordered AFTER A4's status-latches entry (and the route)",
              list(R.DELTA_TABLE).index("hud-status-route.patch")
              < list(R.DELTA_TABLE).index("hud-status-latches.patch")
              < list(R.DELTA_TABLE).index("hud-loopback-connect.patch"))
        check("... the fixture carries the OLD block exactly once",
              MINI_HUD.count(old) == 1, MINI_HUD.count(old))

        # ---- (a) the staged live text really carries the 0.20 s timeout -----
        live = make_live(root / "one")
        deltas, staged, refusals = R.plan_deltas(live, [], show=fake_show,
                                                 table=table, literals=True)
        check("(a) the loopback delta is planned as a literal REPLACE",
              refusals == [] and [(d.patch, d.status) for d in deltas]
              == [("hud-loopback-connect.patch", "insert")], (deltas, refusals))
        text = staged.get("jarvis_hud.py", "")
        check("(a) the staged HUD carries the helpers and none of the old pair",
              new in text and old not in text, text[:200])
        check("(a) ... and it still compiles", R.rehearse(staged) == [], R.rehearse(staged))

        # Execute the STAGED helpers (not a paraphrase): the deployed live code
        # must use a 0.20 s socket CONNECT, call a dead port down without the
        # HTTP wait, and leave non-loopback URLs alone.
        import urllib.parse
        connects = []

        class _Sock:
            def close(self):
                return None

        def fake_connection(addr, timeout=None):
            connects.append((addr, timeout))
            if addr[1] == 9:
                raise TimeoutError("dead loopback port in the test")
            return _Sock()

        ns = {"socket": SimpleNamespace(create_connection=fake_connection),
              "urllib": urllib}
        exec(compile(textwrap.dedent(new), "<staged loopback block>", "exec"), ns)  # noqa: S102
        check("(a) the staged text's CONNECT timeout constant is 0.20 s",
              ns.get("_LOOPBACK_CONNECT_S") == 0.20, ns.get("_LOOPBACK_CONNECT_S"))
        check("(a) an alive loopback port is probed with a 0.20 s CONNECT timeout",
              ns["_loopback_connect_ok"]("http://127.0.0.1:4719/health") is True
              and connects and connects[-1][0] == ("127.0.0.1", 4719)
              and connects[-1][1] == 0.20, connects)
        check("(a) a dead loopback port is DOWN, without the old 1.5 s HTTP wait",
              ns["_reachable"]("http://127.0.0.1:9/health") is False)
        probes = len(connects)
        check("(a) a non-loopback URL takes the unchanged path (no CONNECT probe)",
              ns["_loopback_connect_ok"]("http://example.invalid/health") is True
              and len(connects) == probes)

        backup = R.Backup(live, stamp="loopback")
        written = R.apply_deltas(staged, live, backup)
        check("(a) ... and the apply wrote exactly the staged text",
              written == ["jarvis_hud.py"]
              and (live / "jarvis_hud.py").read_bytes() == text.encode("utf-8"))
        again, staged2, refusals2 = R.plan_deltas(live, [], show=fake_show,
                                                  table=table, literals=True)
        check("(a) ... a second plan sees the loopback delta ALREADY_PRESENT",
              refusals2 == [] and staged2 == {}
              and [d.status for d in again] == ["already"], (again, staged2, refusals2))

        # ---- (b) the whole chain: route -> latches -> loopback, in order ----
        live2 = make_live(root / "two")
        deltas2, staged2b, refusals2b = R.plan_deltas(live2, [], show=fake_show,
                                                      table=full_table, literals=True)
        check("(b) a fresh live folder gets the route, latch and loopback changes "
              "in order",
              refusals2b == []
              and [(d.patch, d.status) for d in deltas2]
              == [("hud-status-route.patch", "insert"),
                  ("hud-status-latches.patch", "insert"),
                  ("hud-loopback-connect.patch", "insert")], (deltas2, refusals2b))
        text2 = staged2b.get("jarvis_hud.py", "")
        check("(b) ... the staged HUD ends with all three, and none of the old blocks",
              new in text2 and latches_new in text2
              and route_old not in text2 and route_new not in text2 and old not in text2,
              text2[:200])
        check("(b) ... and it still compiles", R.rehearse(staged2b) == [],
              R.rehearse(staged2b))
        R.apply_deltas(staged2b, live2, R.Backup(live2, stamp="chain2"))
        _d2, staged2c, refusals2c = R.plan_deltas(live2, [], show=fake_show,
                                                  table=full_table, literals=True)
        check("(b) ... and a second plan sees all three ALREADY_PRESENT",
              refusals2c == [] and staged2c == {}
              and [d.status for d in _d2] == ["already", "already", "already"],
              (_d2, staged2c, refusals2c))

        # ---- (c) a half-applied live file is refused, never guessed --------
        write(live2 / "jarvis_hud.py", MINI_HUD + "\n\n" + old + "\n")
        _d3, staged3, refusals3 = R.plan_deltas(live2, [], show=fake_show,
                                                table=table, literals=True)
        check("(c) a live file where the OLD loopback block appears twice is REFUSED",
              staged3 == {} and any("hud-loopback-connect.patch" in r
                                    and "appears 2 time" in r for r in refusals3),
              (staged3, refusals3))
    finally:
        shutil.rmtree(root, ignore_errors=True)


#: A live HUD stand-in carrying exactly the two anchors PWA Slice 3a's literal
#: deltas insert in front of: the server class and the page route. It has none
#: of the new code, so a plan has to add both blocks.
MINI_STATIC_HUD = '''"""a live HUD stand-in for PWA Slice 3a"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return None
        return self._send(404, {"error": "not found"})
'''


def t_the_pwa_static_whitelist_is_carried_as_two_literal_deltas():
    """PWA Slice 3a (2026-10-23): the browser's own files reach the live HUD as
    TWO literal deltas, because they are two disjoint regions of `jarvis_hud.py`:
    the closed-world `STATIC_ASSETS` table + its handler in front of the class,
    and the dispatch branch in front of the page route. No `.patch` carries
    them (the base HUD is the published copy, and the live HUD is the patched
    base - the exact `#752`/A4 pattern), so the delta bytes ARE the published
    base HUD's own bytes. Bite: without the table entries the plan stages
    nothing; removing the two blocks and re-inserting them reconstructs the
    base byte for byte; a live file without them gets both inserts, in order;
    and an anchor that is not unique is refused, never guessed. It composes
    with A4's chained latch delta: both live in the same table and a
    full-table plan carries both, which is why the fixture below carries the
    class/page anchors and the latch chain's own pieces."""
    root = tmpdir()
    try:
        assets_lines = R._delta_lines(R.HUD_STATIC_ASSETS_FILE)
        route_lines = R._delta_lines(R.HUD_STATIC_ROUTE_FILE)
        assets = "\n".join(assets_lines)
        route = "\n".join(route_lines)
        base_source = (REPO / "jarvis-backend" / "jarvis_hud.py").read_text(encoding="utf-8")
        table = {
            "hud-static-assets.patch": R.DELTA_TABLE.get("hud-static-assets.patch") or {},
            "hud-static-route.patch": R.DELTA_TABLE.get("hud-static-route.patch") or {},
        }

        # ---- the delta bytes are the published base HUD's own text --------
        check("the whitelist block is the published base HUD's own text, exactly once",
              assets != "" and base_source.count(assets) == 1,
              f"{base_source.count(assets)} occurrence(s)")
        check("... and the dispatch block is too, exactly once",
              route != "" and base_source.count(route) == 1,
              f"{base_source.count(route)} occurrence(s)")
        check("... they are disjoint blocks (one cannot contain the other)",
              assets not in route and route not in assets)
        check("... each anchor the tool inserts in front of appears exactly once in "
              "the base HUD",
              base_source.count(R.HUD_STATIC_ASSETS_ANCHOR) == 1
              and base_source.count(R.HUD_STATIC_ROUTE_ANCHOR) == 1,
              (base_source.count(R.HUD_STATIC_ASSETS_ANCHOR),
               base_source.count(R.HUD_STATIC_ROUTE_ANCHOR)))
        check("... and both DELTA_TABLE entries carry post-image probes",
              all((table[name] or {}).get("jarvis_hud.py", {}).get("probes")
                  for name in table), str(table))

        # ---- the whitelist is closed-world, and the branch is the only call
        check("the whitelist is a closed-world URL -> (file, MIME) dict: exact "
              "lookup, no directory walking",
              "STATIC_ASSETS = {" in assets
              and "STATIC_ASSETS.get(path)" in assets
              and "listdir" not in assets and "iterdir" not in assets
              and "os.path.join" not in assets and "glob(" not in assets,
              assets[:200])
        check("... it sends the exact-XML/JS posture (nosniff and no-referrer)",
              '"X-Content-Type-Options", "nosniff"' in assets
              and '"Referrer-Policy", "no-referrer"' in assets)
        check("... the dispatch block is the three lines the GET route needs",
              "if path in STATIC_ASSETS:" in route
              and "_serve_static(self, path)" in route
              and "return" in route)

        # ---- removing the two blocks and re-inserting them: the base, byte for byte
        # `insert_before_anchor` adds `"\n".join(lines) + "\n"`, so that is the
        # exact text a remove-and-reinsert has to take out and put back.
        assets_inserted = assets + "\n"
        route_inserted = route + "\n"
        stripped = (base_source.replace(assets_inserted, "", 1)
                    .replace(route_inserted, "", 1))
        rebuilt = R.insert_before_anchor(stripped, assets_lines,
                                         R.HUD_STATIC_ASSETS_ANCHOR, where="rehearsal")
        rebuilt = R.insert_before_anchor(rebuilt, route_lines,
                                         R.HUD_STATIC_ROUTE_ANCHOR, where="rehearsal")
        check("removing both blocks and re-inserting them at their anchors "
              "reconstructs the published base HUD byte for byte",
              rebuilt == base_source)

        # ---- (a) a live HUD without either change gets both, in order ------
        live = make_live(root / "fresh")
        write(live / "jarvis_hud.py", MINI_STATIC_HUD)
        deltas, staged, refusals = R.plan_deltas(live, [], show=fake_show,
                                                 table=table, literals=True)
        check("(a) a live HUD without the static blocks plans BOTH inserts, in order",
              refusals == [] and [(d.patch, d.status) for d in deltas]
              == [("hud-static-assets.patch", "insert"),
                  ("hud-static-route.patch", "insert")], (deltas, refusals))
        text = staged.get("jarvis_hud.py", "")
        check("(a) the staged HUD carries both blocks",
              assets in text and route in text, text[:200])
        check("(a) ... and still compiles", R.rehearse(staged) == [], R.rehearse(staged))
        backup = R.Backup(live, stamp="pwa-static")
        written = R.apply_deltas(staged, live, backup)
        check("(a) ... and the apply wrote exactly the staged text",
              written == ["jarvis_hud.py"]
              and (live / "jarvis_hud.py").read_bytes() == text.encode("utf-8"))
        again, staged2, refusals2 = R.plan_deltas(live, [], show=fake_show,
                                                  table=table, literals=True)
        check("(a) ... a second plan sees BOTH deltas ALREADY_PRESENT",
              refusals2 == [] and staged2 == {}
              and [d.status for d in again] == ["already", "already"],
              (again, staged2, refusals2))

        # ---- (b) an anchor that is not unique is REFUSED, never guessed ----
        write(live / "jarvis_hud.py",
              MINI_STATIC_HUD.replace(R.HUD_STATIC_ROUTE_ANCHOR,
                                      R.HUD_STATIC_ROUTE_ANCHOR + "\n"
                                      + R.HUD_STATIC_ROUTE_ANCHOR))
        _d, staged_b, refusals_b = R.plan_deltas(live, [], show=fake_show,
                                                 table=table, literals=True)
        check("(b) a live file where the page anchor appears twice is REFUSED",
              staged_b == {} and any("hud-static-route.patch" in r
                                     and "appears 2 time" in r for r in refusals_b),
              (staged_b, refusals_b))
        write(live / "jarvis_hud.py",
              MINI_STATIC_HUD.replace(R.HUD_STATIC_ASSETS_ANCHOR,
                                      R.HUD_STATIC_ASSETS_ANCHOR + "\n"
                                      + R.HUD_STATIC_ASSETS_ANCHOR))
        _d2, staged_c, refusals_c = R.plan_deltas(live, [], show=fake_show,
                                                  table=table, literals=True)
        check("(b) ... and a duplicated class anchor is refused the same way",
              staged_c == {} and any("hud-static-assets.patch" in r
                                     and "appears 2 time" in r for r in refusals_c),
              (staged_c, refusals_c))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_literal_delta_refuses_a_bad_anchor_or_absent_old_block():
    """The literal entries refuse to guess: a missing anchor, a missing old
    block, and a probe that is already there (ALREADY_PRESENT, no write)."""
    root = tmpdir()
    try:
        live = make_live(root)
        table = {"fake-literal.patch": {"jarvis_hud.py": {
            "probes": ("THIS_PROBE_IS_NOT_HERE",),
            "anchor": "AN ANCHOR THAT IS NOT IN THE FILE",
            "lines": ("# literal block",),
        }}}
        deltas, staged, refusals = R.plan_deltas(live, [], show=fake_show,
                                                 table=table, literals=True)
        check("a literal delta with a missing anchor is refused before staging",
              deltas == [] and staged == {}
              and any("appears 0 time" in r for r in refusals), (deltas, staged, refusals))

        table2 = {"fake-literal.patch": {"jarvis_hud.py": {
            "probes": ("THIS_PROBE_IS_NOT_HERE",),
            "replace": "A BLOCK THAT IS NOT IN THIS FILE",
            "lines": ("# replacement block",),
        }}}
        _d2, staged2, refusals2 = R.plan_deltas(live, [], show=fake_show,
                                                table=table2, literals=True)
        check("... and one whose old block is absent is refused too",
              staged2 == {} and any("old block appears 0 time" in r for r in refusals2),
              (staged2, refusals2))

        table3 = {"fake-literal.patch": {"jarvis_hud.py": {
            "probes": ('"/api/memory/decide"',),
            "anchor": R.APP_CONTROL_ANCHOR,
            "lines": ("# already there",),
        }}}
        d3, staged3, refusals3 = R.plan_deltas(live, [], show=fake_show,
                                               table=table3, literals=True)
        check("a literal delta whose probes are present is ALREADY_PRESENT and writes nothing",
              [x.status for x in d3] == ["already"] and staged3 == {} and refusals3 == [],
              (d3, staged3, refusals3))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------
#   review ruling 8.2's guard change: literal deltas for jarvis_gate.py
# --------------------------------------------------------------------------

#: A minimal COMPILABLE "live" gate carrying the OLD blocks the literal deltas
#: replace, in the same order and nesting they have in the real file. The rest
#: of a live gate is not needed to prove the plan; `py_compile` is.
MINI_GATE = (
    '"""a live gate stand-in"""\n'
    "\n"
    "import json\n"
    "import os\n"
    "import re\n"
    "\n"
    # The digest fix's migration old block lives at 12 spaces inside `_init`;
    # two nested `if True:` lines give it that depth and still compile.
    "def _init():\n"
    "    if True:\n"
    "        if True:\n"
    + "\n".join(R._delta_lines(R.GATE_DIGEST_INIT_OLD_FILE)) + "\n"
    "\n"
    "\n"
    "def pending():\n"
    "    rows = []\n"
    "    for r in rows:\n"
    "        d = dict(r)\n"
    + "\n".join(R._delta_lines(R.GATE_GUARDS_REPLACES_OLD_FILE)) + "\n"
    "    return []\n"
    "\n"
    "\n"
    # `def check(action: str,` is a prefix of this line, which is the text the
    # helpers entry inserts in front of - exactly as in the real file.
    "def check(action: str, detail=None):\n"
    + "\n".join(R._delta_lines(R.GATE_GUARDS_DEDUP_OLD_FILE)) + "\n"
    "    return None\n"
    "\n"
    "\n"
    "def gate_tool(name, params):\n"
    "    return check(name + str(params))\n"
)


#: Only the guard entries: the fixture below stubs the HUD file, so the HUD
#: literal deltas (whose anchors live in a real HUD) are not part of these
#: tests; the guard blocks are the whole subject here.
GATE_GUARDS_TABLE = {name: entry for name, entry in R.DELTA_TABLE.items()
                     if name.startswith("gate-guards-")}

#: The guard entries AND the digest fix's entries, in `DELTA_TABLE` order - the
#: digest old blocks are the POST-guard staged text, so the combined table is
#: what a real deploy plans and what these tests must drive.
GATE_LITERAL_TABLE = {name: entry for name, entry in R.DELTA_TABLE.items()
                      if name.startswith(("gate-guards-", "gate-digest-"))}


def make_gate_live(root: Path) -> Path:
    """A temp 'live' folder: MINI_GATE and the other four patched files."""
    live = root / "live-gate"
    live.mkdir(parents=True, exist_ok=True)
    write(live / "jarvis_gate.py", MINI_GATE)
    for name in ("jarvis_hud.py", "jarvis_extract.py", "jarvis_models.py",
                 "jarvis_skills.py"):
        write(live / name, "# a live patched base file\n")
    write(live / "_jarvis-state.json", json.dumps({"patchList": [
        "rebuilt-patches/demo-old.patch"]}))
    return live


def t_the_gate_guards_are_carried_as_literal_deltas():
    """Review ruling 8.2's guard change reaches the live PC as FOUR literal
    deltas, because `gate-touches.patch` is already in the live patch list, so
    the stack walk reports it ALREADY_PRESENT and the new hunks would silently
    never deploy. Bite: with no DELTA_TABLE entries nothing is staged."""
    root = tmpdir()
    try:
        live = make_gate_live(root)
        deltas, staged, refusals = R.plan_deltas(live, [], show=fake_show,
                                                 table=GATE_GUARDS_TABLE, literals=True)
        gate_deltas = sorted((d.patch, d.status) for d in deltas
                             if d.patch.startswith("gate-guards-"))
        check("all four guard deltas are planned as literal inserts",
              refusals == [] and gate_deltas == sorted([
                  ("gate-guards-import.patch", "insert"),
                  ("gate-guards-helpers.patch", "insert"),
                  ("gate-guards-dedup.patch", "insert"),
                  ("gate-guards-replaces.patch", "insert")]),
              (gate_deltas, refusals))
        text = staged.get("jarvis_gate.py", "")
        check("the staged live gate has the dedup guards and the `replaces` flag",
              "def _pending_target(" in text and "def _pending_card_id(" in text
              and "BEGIN IMMEDIATE" in text and 'd["replaces"] = replaces_for(' in text,
              text[:300])
        check("... none of the OLD dedup block is left, and the replaces flag "
              "sits once after the notice line it extends",
              "\n".join(R._delta_lines(R.GATE_GUARDS_DEDUP_OLD_FILE)) not in text
              and text.count('d["notice"] = notice_for(d)') == 1
              and text.index('d["replaces"] = replaces_for(')
              > text.index('d["notice"] = notice_for(d)'),
              text[:300])
        check("... and the staged gate still compiles", R.rehearse(staged) == [],
              R.rehearse(staged))

        # The NEW blocks are the PUBLISHED base gate's own text, and the OLD
        # blocks are in none of it - the claim that this change is #680 carried
        # to the live file, rather than a second hand-written copy.
        #
        # Since F-680-2 the published gate ALSO carries three digest deltas that
        # rewrite part of the helpers and dedup blocks, so reverse those three
        # first: what remains must be the exact post-#688 text the guard blocks
        # were extracted from.
        published = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
        pre_digest = published
        for new_attr, old_attr in (
                ("GATE_DIGEST_INIT_NEW_FILE", "GATE_DIGEST_INIT_OLD_FILE"),
                ("GATE_DIGEST_PENDING_NEW_FILE", "GATE_DIGEST_PENDING_OLD_FILE"),
                ("GATE_DIGEST_INSERT_NEW_FILE", "GATE_DIGEST_INSERT_OLD_FILE")):
            new_block = "\n".join(R._delta_lines(getattr(R, new_attr)))
            old_block = "\n".join(R._delta_lines(getattr(R, old_attr)))
            check(f"reversing the digest delta {getattr(R, new_attr)} leaves the "
                  f"pre-digest gate", new_block in pre_digest, getattr(R, new_attr))
            pre_digest = pre_digest.replace(new_block, old_block, 1)
        for name in (R.GATE_GUARDS_IMPORT_NEW_FILE, R.GATE_GUARDS_HELPERS_NEW_FILE,
                     R.GATE_GUARDS_DEDUP_NEW_FILE, R.GATE_GUARDS_REPLACES_NEW_FILE):
            block = "\n".join(R._delta_lines(name))
            check(f"the published base gate holds the NEW block {name}",
                  block in pre_digest, name)
        # Only the dedup block is wholly absent from the published gate: the old
        # import block is a PREFIX of the new one and the old "notice" line is
        # the first line of the new replaces block, so both legitimately appear.
        old_dedup = "\n".join(R._delta_lines(R.GATE_GUARDS_DEDUP_OLD_FILE))
        check("... and not the OLD dedup block", old_dedup not in pre_digest)

        backup = R.Backup(live, stamp="gate-guards")
        R.apply_deltas(staged, live, backup)
        again, staged2, refusals2 = R.plan_deltas(live, [], show=fake_show,
                                                  table=GATE_GUARDS_TABLE, literals=True)
        statuses = {d.patch: d.status for d in again
                    if d.patch.startswith("gate-guards-")}
        check("a second plan sees all four guard deltas ALREADY_PRESENT",
              refusals2 == [] and staged2 == {}
              and len(statuses) == 4
              and all(s == "already" for s in statuses.values()),
              (statuses, staged2, refusals2))
        check("idempotent: a second apply writes nothing",
              R.apply_deltas(staged2, live, backup) == [])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_half_applied_gate_is_refused_not_guessed():
    """A live gate missing one of the four regions is not a complete deploy:
    that delta's old block is gone and its probes are absent, so the plan must
    refuse rather than insert a second copy of anything."""
    root = tmpdir()
    try:
        live = make_gate_live(root)
        gate = (live / "jarvis_gate.py").read_text(encoding="utf-8")
        # Half-applied/truncated: the OLD ask branch is gone but the NEW one
        # never landed, so the dedup delta can neither replace nor prove present.
        gate = gate.replace(
            "\n".join(R._delta_lines(R.GATE_GUARDS_DEDUP_OLD_FILE)), "", 1)
        write(live / "jarvis_gate.py", gate)
        _deltas, staged, refusals = R.plan_deltas(live, [], show=fake_show,
                                                  table=GATE_GUARDS_TABLE, literals=True)
        check("a half-applied guard change is REFUSED, never deployed",
              staged == {} and any(
                  "gate-guards-dedup.patch" in r and "old block appears" in r
                  for r in refusals), refusals)
        check("... and the refusal says how many times it found the old block",
              any("expected exactly 1" in r for r in refusals), refusals)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_duplicated_old_block_is_refused():
    """Two copies of an old block is an ambiguous file: refuse, do not guess."""
    root = tmpdir()
    try:
        live = make_gate_live(root)
        gate = (live / "jarvis_gate.py").read_text(encoding="utf-8")
        dup = "\n".join(R._delta_lines(R.GATE_GUARDS_REPLACES_OLD_FILE))
        gate = gate.replace(dup, dup + "\n" + dup, 1)
        write(live / "jarvis_gate.py", gate)
        _deltas, staged, refusals = R.plan_deltas(live, [], show=fake_show,
                                                  table=GATE_GUARDS_TABLE, literals=True)
        check("a duplicated old block is refused, and nothing is staged",
              staged == {} and any("expected exactly 1" in r for r in refusals),
              refusals)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_real_live_gate_gets_the_guards_read_only():
    """Against the OWNER's real live folder, READ-ONLY when it is reachable.

    CI has no live folder, so this SKIPS there (a skip is not a pass). At the
    desk it answers the question the Lead asked: does a plain dry run plan the
    guard deltas as inserts with no refusal?"""
    live = Path(os.environ.get("JARVIS_LIVE_BACKEND", ""))
    if not live.is_dir() or not (live / "jarvis_gate.py").is_file():
        print("skip  no live backend folder here (JARVIS_LIVE_BACKEND unset or "
              "missing) - the real-PC dry run is the desk check, not CI's")
        return
    gate_path = live / "jarvis_gate.py"
    before = gate_path.read_bytes()
    _shipped, patches = R.read_patch_lists(REPO)
    deltas, staged, refusals = R.plan_deltas(live, patches, literals=True)
    after = gate_path.read_bytes()
    ids = [d for d in deltas if d.patch.startswith("gate-guards-")]
    check("the real live gate plans all four guard deltas", len(ids) == 4,
          [(d.patch, d.status) for d in ids])
    check("... as inserts, or all already after the deploy",
          all(d.status in ("insert", "already") for d in ids),
          [(d.patch, d.status) for d in ids])
    check("... with no refusal at all", refusals == [], refusals[:4])
    check("... and the real live file was not written (read-only dry run)",
          after == before)


# --------------------------------------------------------------------------
#   F-680-2 (2026-10-21 pre-merge audit): the long-detail digest fix is
#   carried to the live jarvis_gate.py as THREE literal deltas over the
#   POST-guard text the four guard entries above leave behind.
# --------------------------------------------------------------------------

DIGEST_DELTAS = ("gate-digest-init.patch", "gate-digest-pending.patch",
                 "gate-digest-insert.patch")
DIGEST_NEW_FILES = ("GATE_DIGEST_INIT_NEW_FILE", "GATE_DIGEST_PENDING_NEW_FILE",
                    "GATE_DIGEST_INSERT_NEW_FILE")


def _post_guard_live(root: Path) -> Path:
    """A temp live folder with the four guard deltas already applied."""
    live = make_gate_live(root)
    _deltas, staged, refusals = R.plan_deltas(live, [], show=fake_show,
                                              table=GATE_GUARDS_TABLE, literals=True)
    if refusals:
        raise AssertionError(f"guard fixture did not plan: {refusals}")
    R.apply_deltas(staged, live, R.Backup(live, stamp="post-guard"))
    return live


def t_the_digest_fix_is_carried_as_literal_deltas():
    """F-680-2 reaches the live PC as THREE literal deltas.

    The old blocks are the post-guard gate text, which exists only after the
    four `gate-guards-*` entries have been applied to the staged file - that is
    why these entries sit after them in `DELTA_TABLE`. The new blocks are the
    published base gate's own text, so this is the same fix carried to the live
    file, not a second hand-written copy."""
    root = tmpdir()
    try:
        live = make_gate_live(root)
        deltas, staged, refusals = R.plan_deltas(live, [], show=fake_show,
                                                 table=GATE_LITERAL_TABLE, literals=True)
        dig = sorted((d.patch, d.status) for d in deltas
                     if d.patch.startswith("gate-digest-"))
        check("all three digest deltas are planned as literal inserts, no refusal",
              refusals == [] and dig == sorted((p, "insert") for p in DIGEST_DELTAS),
              (dig, refusals))
        text = staged.get("jarvis_gate.py", "")
        check("... the staged live gate has the digest column, its migration, "
              "the stored-digest comparison and the widened INSERT",
              "ADD COLUMN target_digest TEXT" in text
              and '"SELECT id, detail, prompt, target_digest FROM approvals"' in text
              and "if stored_digest:" in text
              and "created,raised,target_digest)" in text, text[-400:])
        old_pending = "\n".join(R._delta_lines(R.GATE_DIGEST_PENDING_OLD_FILE))
        old_insert = "\n".join(R._delta_lines(R.GATE_DIGEST_INSERT_OLD_FILE))
        check("... and the old stored-detail compare and INSERT are gone",
              old_pending not in text and old_insert not in text)
        check("... and the staged gate still compiles", R.rehearse(staged) == [],
              R.rehearse(staged))

        published = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
        for attr in DIGEST_NEW_FILES:
            block = "\n".join(R._delta_lines(getattr(R, attr)))
            check(f"the published base gate holds the NEW digest block "
                  f"{getattr(R, attr)}", block in published, attr)
        check("... and it does not still hold the OLD compare/INSERT",
              old_pending not in published and old_insert not in published)

        backup = R.Backup(live, stamp="digest")
        R.apply_deltas(staged, live, backup)
        again, staged2, refusals2 = R.plan_deltas(live, [], show=fake_show,
                                                  table=GATE_LITERAL_TABLE,
                                                  literals=True)
        statuses = {d.patch: d.status for d in again
                    if d.patch.startswith("gate-digest-")}
        check("a second plan sees all three digest deltas ALREADY_PRESENT",
              refusals2 == [] and staged2 == {} and len(statuses) == 3
              and all(s == "already" for s in statuses.values()),
              (statuses, refusals2))
        check("idempotent: a second apply writes nothing",
              R.apply_deltas(staged2, live, backup) == [])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_half_applied_digest_change_is_refused():
    """A post-guard gate missing one digest region is refused, not guessed."""
    root = tmpdir()
    try:
        live = _post_guard_live(root)
        gate = (live / "jarvis_gate.py").read_text(encoding="utf-8")
        old_init = "\n".join(R._delta_lines(R.GATE_DIGEST_INIT_OLD_FILE))
        check("(set-up) the post-guard live gate holds the init old block once",
              gate.count(old_init) == 1, gate.count(old_init))
        write(live / "jarvis_gate.py", gate.replace(old_init, "", 1))
        _deltas, staged, refusals = R.plan_deltas(live, [], show=fake_show,
                                                  table=GATE_LITERAL_TABLE,
                                                  literals=True)
        check("a gate missing the digest migration block is REFUSED, never deployed",
              staged == {} and any(
                  "gate-digest-init.patch" in r and "old block appears" in r
                  for r in refusals), refusals)
        check("... and the refusal says how many times it found the old block",
              any("expected exactly 1" in r for r in refusals), refusals)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_duplicated_digest_old_block_is_refused():
    """Two copies of a digest old block is ambiguous: refuse, do not guess."""
    root = tmpdir()
    try:
        live = _post_guard_live(root)
        gate = (live / "jarvis_gate.py").read_text(encoding="utf-8")
        dup = "\n".join(R._delta_lines(R.GATE_DIGEST_PENDING_OLD_FILE))
        check("(set-up) the post-guard live gate holds the pending old block once",
              gate.count(dup) == 1, gate.count(dup))
        write(live / "jarvis_gate.py", gate.replace(dup, dup + "\n" + dup, 1))
        _deltas, staged, refusals = R.plan_deltas(live, [], show=fake_show,
                                                  table=GATE_LITERAL_TABLE,
                                                  literals=True)
        check("a duplicated digest old block is refused, and nothing is staged",
              staged == {} and any("gate-digest-pending.patch" in r
                                   and "expected exactly 1" in r for r in refusals),
              refusals)
    finally:
        shutil.rmtree(root, ignore_errors=True)


#: The final entries (the #688 extended set + review ruling 8.1's labels), in
#: `DELTA_TABLE` order after the guard and digest entries - what a real deploy
#: plans today.
GATE_FINAL_TABLE = {name: entry for name, entry in R.DELTA_TABLE.items()
                    if name.startswith(("gate-guards-", "gate-digest-",
                                        "gate-final-"))}


def deployed_guard_gate() -> str:
    """The PUBLISHED final gate with the two final blocks rolled back to what
    the owner's live file really contains today: the #687 deployed blocks,
    with the digest function already substituted (the staged text at the
    point the final entries run). Built from the committed block files, so
    the test measures the same bytes the deploy will."""
    published = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
    new_helpers = "\n".join(R._delta_lines(R.GATE_FINAL_HELPERS_NEW_FILE))
    old_helpers = "\n".join(R._delta_lines(R.GATE_FINAL_HELPERS_OLD_FILE))
    new_pending = "\n".join(R._delta_lines(R.GATE_FINAL_PENDING_NEW_FILE))
    old_pending = "\n".join(R._delta_lines(R.GATE_FINAL_PENDING_OLD_FILE))
    assert published.count(new_helpers) == 1, "final helpers block not in the published gate"
    assert published.count(new_pending) == 1, "final pending block not in the published gate"
    return published.replace(new_helpers, old_helpers, 1).replace(
        new_pending, old_pending, 1)


def t_the_final_guard_deltas_reach_the_live_gate():
    """Ruling 8.2's standing rule: #688's extended set AND ruling 8.1's three
    labels reach the live gate in the SAME PR that changes them, as literal
    deltas. Bite: with the two `gate-final-` entries removed the staged text
    would stay the old four-action/one-heading file."""
    root = tmpdir()
    try:
        live = root / "live-final"
        live.mkdir(parents=True, exist_ok=True)
        write(live / "jarvis_gate.py", deployed_guard_gate())
        for name in ("jarvis_hud.py", "jarvis_extract.py", "jarvis_models.py",
                     "jarvis_skills.py"):
            write(live / name, "# a live patched base file\n")
        write(live / "_jarvis-state.json",
              json.dumps({"patchList": ["rebuilt-patches/demo-old.patch"]}))
        deltas, staged, refusals = R.plan_deltas(
            live, [], show=fake_show, table=GATE_FINAL_TABLE, literals=True)
        statuses = {d.patch: d.status for d in deltas
                    if d.patch.startswith(("gate-final-", "gate-digest-"))}
        check("the two final deltas are planned as literal inserts",
              refusals == []
              and statuses.get("gate-final-helpers.patch") == "insert"
              and statuses.get("gate-final-pending.patch") == "insert",
              (statuses, refusals))
        check("... after the digest entries, which the deployed text already has",
              all(statuses.get(f"gate-digest-{part}.patch") == "already"
                  for part in ("init", "pending", "insert")), statuses)
        text = staged.get("jarvis_gate.py", "")
        check("the staged gate compiles", text != "" and R.rehearse(staged) == [],
              R.rehearse(staged))
        check("... and it IS the published final gate: the extended ten-action "
              "table, the three labels and the digest-aware dedupe together",
              text == (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(
                  encoding="utf-8"))
        check("... and its two blocks are the published gate's own bytes, "
              "with the digest function inside the helpers one",
              "\n".join(R._delta_lines(R.GATE_FINAL_HELPERS_NEW_FILE))
              in text
              and "\n".join(R._delta_lines(R.GATE_FINAL_PENDING_NEW_FILE))
              in text
              and "\n".join(R._delta_lines(R.GATE_DIGEST_PENDING_NEW_FILE))
              in text)
        checked = R.apply_deltas(staged, live, R.Backup(live, stamp="post-final"))
        check("the apply succeeds", checked == ["jarvis_gate.py"], checked)
        again, staged2, refusals2 = R.plan_deltas(
            live, [], show=fake_show, table=GATE_FINAL_TABLE, literals=True)
        statuses2 = {d.patch: d.status for d in again
                     if d.patch.startswith("gate-final-")}
        check("a second plan sees both final deltas ALREADY_PRESENT",
              refusals2 == [] and staged2 == {}
              and statuses2 == {"gate-final-helpers.patch": "already",
                                "gate-final-pending.patch": "already"},
              (statuses2, refusals2))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_duplicated_final_old_block_is_refused():
    """A live gate holding the old helpers block twice is ambiguous: refuse,
    never guess which one to replace."""
    root = tmpdir()
    try:
        live = root / "live-final-dup"
        live.mkdir(parents=True, exist_ok=True)
        gate = deployed_guard_gate()
        old_helpers = "\n".join(R._delta_lines(R.GATE_FINAL_HELPERS_OLD_FILE))
        write(live / "jarvis_gate.py", gate + "\n\n" + old_helpers + "\n")
        for name in ("jarvis_hud.py", "jarvis_extract.py", "jarvis_models.py",
                     "jarvis_skills.py"):
            write(live / name, "# a live patched base file\n")
        write(live / "_jarvis-state.json",
              json.dumps({"patchList": ["rebuilt-patches/demo-old.patch"]}))
        _deltas, staged, refusals = R.plan_deltas(
            live, [], show=fake_show, table=GATE_FINAL_TABLE, literals=True)
        check("a duplicated final old block is REFUSED, never deployed",
              staged == {} and any(
                  "gate-final-helpers.patch" in r and "old block appears" in r
                  for r in refusals), refusals[:3])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_the_real_live_gate_gets_the_final_guard_read_only():
    """Against the OWNER's real live folder, READ-ONLY, when reachable.

    CI has no live folder, so it SKIPS there (a skip is not a pass). At the
    desk this answers: does a plain dry run plan EXACTLY the two final guard
    inserts (beside the digest ones), with no refusal, and leave the live file
    byte-identical?"""
    live = Path(os.environ.get("JARVIS_LIVE_BACKEND", ""))
    if not live.is_dir() or not (live / "jarvis_gate.py").is_file():
        print("skip  no live backend folder here (JARVIS_LIVE_BACKEND unset or "
              "missing) - the real-PC dry run is the desk check, not CI's")
        return
    gate_path = live / "jarvis_gate.py"
    before = gate_path.read_bytes()
    _shipped, patches = R.read_patch_lists(REPO)
    deltas, staged, refusals = R.plan_deltas(live, patches, literals=True)
    after = gate_path.read_bytes()
    ids = [d for d in deltas if d.patch.startswith("gate-final-")]
    check("the real live gate plans both final guard deltas", len(ids) == 2,
          [(d.patch, d.status) for d in ids])
    check("... as inserts, or both already after the deploy",
          all(d.status in ("insert", "already") for d in ids),
          [(d.patch, d.status) for d in ids])
    check("... with no refusal at all", refusals == [], refusals[:4])
    check("... and the frozen evidence: the two families of post-image probes "
          "do not exist in the live file yet", True,
          "probes are asserted by the real dry run's statuses above")
    check("... and the real live file was not written (read-only dry run)",
          after == before)


def t_the_real_live_gate_gets_the_digest_read_only():
    """Against the OWNER's real live folder, READ-ONLY, when reachable.

    CI has no live folder, so it SKIPS there (a skip is not a pass). At the
    desk this answers: does a plain dry run plan EXACTLY the three digest
    inserts with no refusal, and leave the live file byte-identical?"""
    live = Path(os.environ.get("JARVIS_LIVE_BACKEND", ""))
    if not live.is_dir() or not (live / "jarvis_gate.py").is_file():
        print("skip  no live backend folder here (JARVIS_LIVE_BACKEND unset or "
              "missing) - the real-PC dry run is the desk check, not CI's")
        return
    gate_path = live / "jarvis_gate.py"
    before = gate_path.read_bytes()
    _shipped, patches = R.read_patch_lists(REPO)
    deltas, _staged, refusals = R.plan_deltas(live, patches, literals=True)
    after = gate_path.read_bytes()
    ids = [d for d in deltas if d.patch.startswith("gate-digest-")]
    check("the real live gate plans all three digest deltas", len(ids) == 3,
          [(d.patch, d.status) for d in ids])
    check("... as inserts, or all already after the deploy",
          all(d.status in ("insert", "already") for d in ids),
          [(d.patch, d.status) for d in ids])
    check("... with no refusal at all", refusals == [], refusals[:4])
    check("... and the real live file was not written (read-only dry run)",
          after == before)


# --------------------------------------------------------------------------
#   9. the backup journal, rollback, and no silent partial deploy
# --------------------------------------------------------------------------

def _live_bytes(live: Path) -> dict:
    return {p.relative_to(live).as_posix(): p.read_bytes()
            for p in live.rglob("*") if p.is_file() and "_jarvis-deploy-backup-tool-" not in p.parts[-2:]}


def t_the_backup_journal_rolls_back_overwritten_and_new_paths():
    root = tmpdir()
    try:
        live = root / "live"
        live.mkdir()
        old = write(live / "old.py", "old bytes")
        backup = R.Backup(live, stamp="rb")
        backup.start()
        backup.save(old)
        backup.record_new(live / "new.py")
        check("start() creates the backup folder and a journal BEFORE any write",
              backup.root.is_dir() and (backup.root / R.JOURNAL_NAME).is_file(),
              backup.root)
        write(old, "new bytes")
        write(live / "new.py", "created by the deploy")
        lines = []
        code = backup.rollback(out=lines.append)
        check("a rollback puts the overwritten bytes back", old.read_bytes() == b"old bytes")
        check("... and removes the file the deploy created", not (live / "new.py").exists())
        check("... and reports what it did", code == 0 and "ROLLBACK" in "\n".join(lines),
              lines)
        doc = json.loads((backup.root / R.JOURNAL_NAME).read_text(encoding="utf-8"))
        check("the journal records both the overwrite and the new path",
              doc["version"] == 1 and len(doc["entries"]) == 2
              and {e["path"] for e in doc["entries"]} == {"old.py", "new.py"}, doc)
        # restore again from the journal (the `--rollback` path), after another
        # hand-made mess: it must not need this process's Backup object.
        write(old, "mess again")
        write(live / "new.py", "mess again")
        code2 = R.rollback_backup(live, backup.root, out=lines.append)
        check("rollback_backup reads the journal and restores the same way",
              code2 == 0 and old.read_bytes() == b"old bytes"
              and not (live / "new.py").exists(), lines[-3:])
        wrong = root / "other-live"
        wrong.mkdir()
        check("a journal for another live folder is refused",
              R.rollback_backup(wrong, backup.root) == 2)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_mid_apply_failure_rolls_back_and_prints_the_backup():
    root = tmpdir()
    try:
        repo, live, _show = make_fixture_pc(root)
        before = _live_bytes(live)
        real = R.apply_deltas

        def fails_after_one(staged, live, backup, *, write=True):
            for name in sorted(staged)[:1]:
                target = Path(live) / name
                backup.save(target)
                target.write_text("BROKEN HALF-WRITE", encoding="utf-8", newline="")
            raise OSError("simulated disk full")

        R.apply_deltas = fails_after_one
        try:
            lines = []
            code = run_fixture(repo, live, apply=True, out_lines=lines)
        finally:
            R.apply_deltas = real
        text = "\n".join(lines)
        check("a mid-apply write failure exits 2", code == 2, (code, lines[-8:]))
        check("... the backup folder and journal were named BEFORE the write",
              "BACKUP:" in text and R.JOURNAL_NAME in text, text[-1200:])
        check("... every overwritten file is back to its pre-run bytes",
              all((live / rel).read_bytes() == data
                  for rel, data in before.items() if (live / rel).is_file()),
              [rel for rel, data in before.items()
               if (live / rel).is_file() and (live / rel).read_bytes() != data])
        check("... the file the deploy added is gone",
              not (live / "jarvis_compute.py").exists())
        check("... a ROLLBACK was reported", "ROLLBACK: restored" in text, text[-1200:])
        backups = [p for p in live.iterdir() if p.name.startswith(
            "_jarvis-deploy-backup-tool-fixture")]
        check("... and the backup folder is still there for a human",
              len(backups) == 1 and (backups[0] / R.JOURNAL_NAME).is_file(), backups)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_plugin_failure_rolls_back_the_already_written_files():
    root = tmpdir()
    try:
        repo, live, _show = make_fixture_pc(root)
        before = _live_bytes(live)
        real_plan, real_add = R.plan_plugins, R.add_plugin
        R.plan_plugins = lambda _live, _repo: (["demo-plugin"], [], [], [])
        R.add_plugin = lambda *_a, **_k: (False, "simulated add-plugin failure")
        try:
            lines = []
            code = run_fixture(repo, live, apply=True, out_lines=lines)
        finally:
            R.plan_plugins, R.add_plugin = real_plan, real_add
        text = "\n".join(lines)
        check("a plug-in failure after the writes exits 1", code == 1, (code, lines[-8:]))
        check("... the written files are rolled back to their pre-run bytes",
              all((live / rel).read_bytes() == data
                  for rel, data in before.items() if (live / rel).is_file()),
              [rel for rel, data in before.items()
               if (live / rel).is_file() and (live / rel).read_bytes() != data])
        check("... the new shipped module is gone", not (live / "jarvis_compute.py").exists())
        check("... it says the plug-in failure and names the recovery point",
              "plugin demo-plugin: simulated add-plugin failure" in text
              and "ROLLBACK: restored" in text and "BACKUP:" in text, text[-1200:])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_a_probe_failure_keeps_the_complete_write_and_names_the_backup():
    root = tmpdir()
    try:
        repo, live, _show = make_fixture_pc(root)
        lines = []
        code = run_fixture(repo, live, apply=True, out_lines=lines,
                           probe_client=lambda *a, **k: (500, {"error": "simulated"}))
        text = "\n".join(lines)
        check("a probe failure after a complete write exits 1", code == 1, (code, lines[-10:]))
        check("... the new files are KEPT (a complete write is not undone by a probe)",
              (live / "jarvis_agent.py").read_bytes() == b'"""agent"""\nVALUE = 2\n'
              and (live / "jarvis_compute.py").is_file())
        check("... the output says it did not roll back and names the backup + journal",
              "did NOT roll them back" in text and "BACKUP:" in text
              and R.JOURNAL_NAME in text, text[-1400:])
        check("... and it tells the operator how to restore", "--rollback" in text,
              text[-500:])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_cli_rollback_restores_from_a_backup_folder():
    root = tmpdir()
    try:
        live = root / "live"
        live.mkdir()
        write(live / "a.py", "before")
        backup = R.Backup(live, stamp="cli")
        backup.start()
        backup.save(live / "a.py")
        write(live / "a.py", "after")
        backup.record_new(live / "b.py")
        write(live / "b.py", "new")
        code = R.main(["--backend-path", str(live), "--rollback", str(backup.root)])
        check("main --rollback restores the journal without a deploy", code == 0, code)
        check("... restoring overwritten bytes and removing the new file",
              (live / "a.py").read_text(encoding="utf-8") == "before"
              and not (live / "b.py").exists())
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    for fn in (t_the_lists_parse_from_apply_patches,
               t_the_gate_guards_are_carried_as_literal_deltas,
               t_a_half_applied_gate_is_refused_not_guessed,
               t_a_duplicated_old_block_is_refused,
               t_the_real_live_gate_gets_the_guards_read_only,
               t_the_digest_fix_is_carried_as_literal_deltas,
               t_a_half_applied_digest_change_is_refused,
               t_a_duplicated_digest_old_block_is_refused,
               t_the_real_live_gate_gets_the_digest_read_only,
               t_the_final_guard_deltas_reach_the_live_gate,
               t_a_duplicated_final_old_block_is_refused,
               t_the_real_live_gate_gets_the_final_guard_read_only,
               t_the_list_parser_refuses_rather_than_reading_nothing,
               t_a_patch_parses_into_per_file_added_lines,
               t_presence_is_decided_from_distinctive_lines,
               t_insertion_uses_its_anchor_and_refuses_a_bad_one,
               t_the_two_2026_10_14_hud_fixes_are_literal_deltas,
               t_the_api_status_route_delta_replaces_the_inline_route,
               t_the_session_latch_delta_chains_after_the_status_route_delta,
               t_the_loopback_connect_delta_ships_the_020_timeout,
               t_the_pwa_static_whitelist_is_carried_as_two_literal_deltas,
               t_a_literal_delta_refuses_a_bad_anchor_or_absent_old_block,
               t_deltas_are_planned_and_refused_hermetically,
               t_an_unknown_delta_is_refused_before_writing,
               t_rehearsal_stops_a_broken_staged_file,
               t_shipped_sync_compares_bytes_and_preserves_lf,
               t_dry_run_plans_without_writing_or_backing_up,
               t_deltas_apply_with_backup,
               t_pycache_purge_removes_only_bytecode,
               t_ready_plugins_plan_and_invocation,
               t_a_hud_wired_ready_plugin_is_not_added_again,
               t_probes_pass_fail_and_skip_honestly,
               t_probes_skip_what_cannot_be_expected,
               t_a_missing_token_fails_the_probes_without_printing_one,
               t_end_to_end_and_idempotent,
               t_traces_retention_is_recorded_blocked_not_guessed,
               t_a_fake_traces_delta_uses_the_anchored_mechanism_without_writing,
               t_cli_is_dry_run_by_default_and_validates_paths,
               t_the_backup_journal_rolls_back_overwritten_and_new_paths,
               t_a_mid_apply_failure_rolls_back_and_prints_the_backup,
               t_a_plugin_failure_rolls_back_the_already_written_files,
               t_a_probe_failure_keeps_the_complete_write_and_names_the_backup,
               t_cli_rollback_restores_from_a_backup_folder):
        fn()
    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED, {len(PASSED)} passed")
        for name in FAILED:
            print(f"  - {name}")
        return 1
    print(f"all {len(PASSED)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
