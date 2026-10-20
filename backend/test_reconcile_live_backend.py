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
     probes pass.

NOTHING HERE TOUCHES THE REAL LIVE FOLDER. Every path is under a temporary directory; the
only real repository file read is `scripts/apply-patches.ps1` and the two patches the
deploy uses, for the parser tests (read-only).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
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
    for name in ("jarvis_gate.py", "jarvis_extract.py", "jarvis_models.py", "jarvis_skills.py"):
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


def run_fixture(repo: Path, live: Path, *, apply: bool, out_lines=None, **kw):
    out = (out_lines.append if out_lines is not None else (lambda _m: None))

    def client(url, method="GET", body=None, token=""):
        if url.endswith("/api/setup"):
            return 200, {}
        if url.endswith("/api/app-control/run"):
            return 409, {"error": "off"}
        if url.endswith("/api/voice/status"):
            return 200, {"gate": {"training": {}}}
        return 404, {}

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


def main():
    for fn in (t_the_lists_parse_from_apply_patches,
               t_the_list_parser_refuses_rather_than_reading_nothing,
               t_a_patch_parses_into_per_file_added_lines,
               t_presence_is_decided_from_distinctive_lines,
               t_insertion_uses_its_anchor_and_refuses_a_bad_one,
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
               t_cli_is_dry_run_by_default_and_validates_paths):
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
