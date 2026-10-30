"""test_android_builder.py - an app Jarvis builds and sideloads, from the
owner's own words (jarvis_android_builder.py, docs/JARVIS-API.md section 166,
docs/APP-BUILDER-DESIGN.md milestones C, F and G).

    python3 backend/test_android_builder.py

The owner asked on 2026-10-30: "can jarvis build android apps? that i can
sideload into my phone? if not add them". What this proves, with REAL git in a
temporary settings folder and a FAKE gate (no socket opens - a guard fails the
suite if one does):

  - the template: every one of the fixed files is written, with LF endings,
    the validated title, package and colours, and no placeholder left in any
    of them; the two Gradle wrapper files are byte-identical to the ones this
    repository already ships for `jarvis-client`; the written manifest really
    declares NO permission, and the WebView really refuses every navigation;
  - what it refuses: a web project, a missing task, a task that already has a
    project, a name that cannot become a package, a title with a quote in it,
    a colour that is not #RRGGBB, a fourth web file, a huge one, a non-text
    one, and a path hiding in an asset's name;
  - the build: the command is EXACTLY `<task copy>/gradlew.bat assembleDebug`
    in EXACTLY the task copy - not a parameter, not a template, and a plan
    whose argv was tampered with runs nothing; no yes, no run; the time limit;
    a build that fails says so and never claims success without an APK;
  - the environment: a token, a key and a password in the parent's
    environment do NOT reach Gradle or adb, and the three toolchain paths
    DO;
  - the install: adb by FULL PATH and the ONE `install -r <apk>` form - the
    source is scanned for `shell`, `uninstall`, `-s` and `exec-out`, so a
    second adb door cannot be added without failing here; an APK outside the
    task's copy, a file that is not an APK, and an empty file are all refused;
    nothing installs before a build made the file;
  - the cards: ONE at tier "ask" naming the exact command, the folder and the
    APK; a gate that says no, a gate at another tier, a gate whose answer is
    "stale" (rule 4: a stale event stream blocks acting) and a task thrown
    away while its card is up all leave the world untouched and say so;
  - PC only: build, install and the template are refused from the phone with
    403 pc_only, before anything else about the request is read;
  - the wiring: the two gate rows in `jarvis-backend/jarvis_gate.py` (both
    RISKY, both in the no-standing-rule list), the two tier lines in both
    settings files, `jarvis_owner_check` calling both risky, the drop-in
    folder's plugin.json, the module in every list that must carry it, and
    the fact that this feature adds NO patch (so it needs no DELTA_TABLE
    entry and cannot block a deploy).

What this deliberately does NOT do: run a real Gradle build or a real adb
install. Both are measured by hand on the owner's PC, never here - a CI
runner has no Android SDK, no 130 MB of Gradle to download and no phone.

No pytest, no network, no model.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_android_builder.py", "jarvis_app_workspace.py",
                "jarvis_projects.py", "jarvis_child_env.py")

if shutil.which("git") is None:
    print("SKIP  git is not installed here - these tests run real git")
    sys.exit(0)

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-android-builder-"))
_AUDIT = []
_TIER = {"app_build_android": "ask", "app_install_android": "ask"}
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda event, detail=None: _AUDIT.append((event, detail))
fw.action_tier = lambda action: _TIER.get(action, "ask")
sys.modules["jarvis_framework"] = fw
os.environ["JARVIS_TEST_FAKE_TOKEN"] = "must-not-reach-gradle"

_NET = []
_real_connect = socket.socket.connect


def _no_connect(self, *a, **k):
    _NET.append(a)
    raise OSError("test_android_builder.py: no network")


socket.socket.connect = _no_connect

import jarvis_android_builder as A  # noqa: E402
import jarvis_app_workspace as W  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Said:
    """What the approval gate hands back."""

    def __init__(self, outcome="approved", tier="ask", allowed=None, reason=""):
        self.outcome = outcome
        self.tier = tier
        self.allowed = (outcome == "approved") if allowed is None else allowed
        self.reason = reason


class Gate:
    """A fake approval gate: records every card, answers as told."""

    def __init__(self, answer=None, before=None, raises=None):
        self.calls = []
        self.answer = answer if answer is not None else Said()
        self.before = before
        self.raises = raises

    def __call__(self, action, detail, prompt):
        self.calls.append((action, detail, prompt))
        if self.before:
            self.before()
        if self.raises:
            raise self.raises
        return self.answer


def now_spawn(fn):
    fn()


class Held:
    """A spawn that keeps the card's work for later - the card is 'up'."""

    def __init__(self):
        self.fns = []

    def __call__(self, fn):
        self.fns.append(fn)


def _rmtree(path):
    for dirpath, dirnames, filenames in os.walk(path):
        for name in list(dirnames) + list(filenames):
            try:
                os.chmod(os.path.join(dirpath, name), 0o700)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


_N = [0]


def fresh() -> str:
    """A new app called `appN`, of kind "android", with one empty task."""
    _N[0] += 1
    name = f"app{_N[0]}"
    W.create_project(name, "android", f"App {_N[0]}")
    made = W.start_task(name, "Build it", source="empty")
    return name, made["task"]


def written(name, task):
    """The task's copy, after the template has been written into it."""
    tdir = W.task_dir(name, task)
    plan = A.plan_template(name, task)
    assert not plan.refused, plan.refused
    A.write_template(plan)
    return tdir


class FakeToolchain:
    """A real SDK/JDK folder and a fake adb, so no test needs one installed."""

    def __init__(self, root: Path):
        self.sdk = root / "sdk"
        self.java = root / "jdk"
        self.adb = self.sdk / "platform-tools" / "adb.exe"
        for d in (self.sdk, self.java, self.adb.parent):
            d.mkdir(parents=True, exist_ok=True)
        self.adb.write_bytes(b"fake adb")
        self._saved = {}

    def __enter__(self):
        self._saved = {"sdk": A.sdk_root, "java": A.java_home, "adb": A.adb_path,
                       "win": A.WINDOWS}
        A.sdk_root = lambda: self.sdk
        A.java_home = lambda: self.java
        A.adb_path = lambda: self.adb
        A.WINDOWS = True
        return self

    def __exit__(self, *exc):
        A.sdk_root = self._saved["sdk"]
        A.java_home = self._saved["java"]
        A.adb_path = self._saved["adb"]
        A.WINDOWS = self._saved["win"]
        return False


class Ran:
    """A stand-in for A._run: records the command, and makes the APK when the
    command is a build, so nothing real is ever executed."""

    def __init__(self, code=0, make_apk=True, seconds_hit=False):
        self.calls = []
        self.code = code
        self.make_apk = make_apk
        self.seconds_hit = seconds_hit
        self._saved = None

    def __call__(self, argv, cwd, env, seconds, log):
        self.calls.append({"argv": list(argv), "cwd": Path(cwd), "env": dict(env),
                           "seconds": seconds})
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        Path(log).write_text("BUILD SUCCESSFUL\n", encoding="utf-8")
        if self.seconds_hit:
            return -1, Path(log)
        if self.make_apk and len(argv) > 1 and argv[1] == A.GRADLE_TASK:
            apk = Path(cwd) / A.APK_REL
            apk.parent.mkdir(parents=True, exist_ok=True)
            apk.write_bytes(b"PK\x03\x04" + b"x" * 64)
        return self.code, Path(log)

    def __enter__(self):
        self._saved = A._run
        A._run = self
        return self

    def __exit__(self, *exc):
        A._run = self._saved
        return False


# --------------------------------------------------------------------------
#   The values: a package, a title, two colours
# --------------------------------------------------------------------------


def t_package_and_values():
    check("a folder name becomes a legal package",
          A.package_name("my-note-app") == "com.jarvis.made.my_note_app",
          A.package_name("my-note-app"))
    check("a name that starts with a digit still makes a legal package",
          A.package_name("3d-viewer") == "com.jarvis.made.app_3d_viewer",
          A.package_name("3d-viewer"))
    check("two apps cannot collide with someone else's id",
          A.package_name("notes").startswith("com.jarvis.made."))
    for bad in ("Upper", "with space", "", "-leading", "x" * 41, "../escape"):
        raised = False
        try:
            A.package_name(bad)
        except W.WorkspaceError:
            raised = True
        except Exception:
            raised = False
        check(f"refused as an app name: {bad!r}", raised)
    check("a title is tidied and kept",
          A.check_title("  My   Notes  ") == "My Notes")
    for bad in ("It's mine", 'say "hi"', "a<b>c", "", "x" * 41):
        raised = False
        try:
            A.check_title(bad)
        except A.BuildRefused:
            raised = True
        check(f"refused as a title (it goes into an Android string): {bad!r}", raised)
    check("a colour must be #RRGGBB", A.check_colour("#AABBCC", "x") == "#aabbcc")
    raised = False
    try:
        A.check_colour("red", "x")
    except A.BuildRefused:
        raised = True
    check("... and anything else is refused", raised)
    raised = False
    try:
        A._fill("hello __JARVIS_TITLE__", background="#000000")
    except A.BuildRefused:
        raised = True
    check("a template with an unfilled value is refused, never written", raised)


# --------------------------------------------------------------------------
#   The routes
# --------------------------------------------------------------------------


def t_the_route_table():
    base = "/api/projects/p1/app/tasks/abc123abc123"
    check("the status route", A.parse_route(base + "/android") ==
          ("status", "p1", "abc123abc123"))
    for leaf in ("template", "build", "install"):
        check(f"the {leaf} route", A.parse_route(f"{base}/android/{leaf}") ==
              (leaf, "p1", "abc123abc123"))
    for junk in ("/api/projects/p1/app/tasks/t/android/other",
                 "/api/projects/p1/app/tasks/t",
                 "/api/projects/p1/app/tasks/t/android/",
                 "/api/projects/p1/android",
                 "/api/apps/android",
                 "/api/projects/p1/app/tasks/t/files"):
        check(f"not this module's route: {junk}", A.parse_route(junk) is None)
    import jarvis_apps
    check("... and jarvis_apps does not claim them either",
          jarvis_apps.parse_route(base + "/android") is None
          and jarvis_apps.parse_route(base + "/android/build") is None)


# --------------------------------------------------------------------------
#   The template
# --------------------------------------------------------------------------


def t_the_template_writes_the_expected_files():
    name, task = fresh()
    tdir = W.task_dir(name, task)
    plan = A.plan_template(name, task, title="My Notes", background="#102030",
                           accent="#ffcc00")
    check("the plan is not refused", plan.refused == "", plan.refused)
    done = A.write_template(plan)
    check("it reports the files it wrote", done["files"] == len(A.template_paths(name)),
          (done, len(A.template_paths(name))))
    for rel in A.template_paths(name):
        check(f"written: {rel}", (tdir / rel).is_file())
    for rel in ("settings.gradle.kts", "build.gradle.kts", "gradle.properties",
                "gradle/wrapper/gradle-wrapper.properties", "app/build.gradle.kts",
                "app/src/main/AndroidManifest.xml",
                "gradle/wrapper/gradle-wrapper.jar",
                "app/src/main/assets/index.html", "app/src/main/assets/app.js",
                "app/src/main/assets/app.css"):
        data = (tdir / rel).read_bytes()
        if rel.endswith(".jar"):
            check(f"{rel} is the wrapper jar, byte for byte",
                  data == A.wrapper_files()[1].read_bytes())
            continue
        check(f"{rel} is LF-only and has no placeholder left",
              b"\r\n" not in data and b"__JARVIS" not in data, rel)
    # gradlew.bat is GRADLE's own file. The repository stores text as LF, so
    # the copy beside the module is LF; the generated one must be CRLF, because
    # cmd.exe mis-reads labels in an LF-only batch file. Both halves are checked.
    bat = (tdir / "gradlew.bat").read_bytes()
    shipped = A.wrapper_files()[0].read_bytes()
    check("gradlew.bat is Gradle's own file, byte for byte, and still says Apache-2.0",
          bat.replace(b"\r\n", b"\n") == shipped.replace(b"\r\n", b"\n")
          and b"Apache-2.0" in bat)
    check("... and the GENERATED copy has the CRLF endings a Windows batch file needs",
          b"\r\n" in bat and bat.count(b"\n") == bat.count(b"\r\n"), bat[:80])
    manifest = (tdir / "app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    check("the app declares NO permission at all - not even INTERNET",
          "android.permission" not in manifest and "<uses-permission" not in manifest)
    check("... and no cleartext traffic either",
          'android:usesCleartextTraffic="false"' in manifest)
    activity = (tdir / "app/src/main/java/com/jarvis/made/"
                f"{name}/MainActivity.kt").read_text(encoding="utf-8")
    check("the activity loads the owner's page from assets",
          'loadUrl("file:///android_asset/index.html")' in activity)
    check("... with file access, content access and every navigation refused",
          "allowFileAccess = false" in activity and "allowContentAccess = false" in activity
          and "shouldOverrideUrlLoading" in activity and "= true" in activity)
    gradle = (tdir / "app/build.gradle.kts").read_text(encoding="utf-8")
    check("the module's build file carries the app's package and the pinned SDK levels",
          f'namespace = "com.jarvis.made.{name}"' in gradle
          and f"compileSdk = {A.COMPILE_SDK}" in gradle
          and f"minSdk = {A.MIN_SDK}" in gradle)
    strings = (tdir / "app/src/main/res/values/strings.xml").read_text(encoding="utf-8")
    check("the phone shows the owner's own name for the app",
          '<string name="app_name">My Notes</string>' in strings, strings)
    colours = (tdir / "app/src/main/res/values/colors.xml").read_text(encoding="utf-8")
    check("... and the window uses the two colours it was given",
          '<color name="jarvis_background">#102030</color>' in colours
          and '<color name="jarvis_accent">#ffcc00</color>' in colours, colours)
    index = (tdir / "app/src/main/assets/index.html").read_text(encoding="utf-8")
    check("with no page given, a WORKING page is written (so a first build is one click)",
          "My Notes" in index and "app.css" in index and "app.js" in index)
    props = (tdir / "gradle/wrapper/gradle-wrapper.properties").read_text(encoding="utf-8")
    check("the wrapper names the Gradle version AND its SHA-256, so a tampered download is "
          "refused rather than run",
          f"gradle-{A.GRADLE_VERSION}-bin.zip" in props
          and A.GRADLE_DIST_SHA256 in props
          and "distributionSha256Sum=" in props)


def t_the_owner_supplies_only_web_files():
    name, task = fresh()
    tdir = W.task_dir(name, task)
    plan = A.plan_template(name, task, assets={
        "index.html": "<h1>mine</h1>", "app.js": "var a=1;", "app.css": "body{}"})
    check("three web files are accepted", plan.refused == "", plan.refused)
    A.write_template(plan)
    check("the owner's own page is the one written",
          (tdir / A.ASSET_DIR / "index.html").read_text(encoding="utf-8") == "<h1>mine</h1>")
    check("... and the fixed files are still the template's",
          "plugins {" in (tdir / "app/build.gradle.kts").read_text(encoding="utf-8"))


def t_the_template_refuses():
    web = "webapp"
    W.create_project(web, "web", "A web app")
    made = W.start_task(web, "Change it", source="empty")
    plan = A.plan_template(web, made["task"])
    check("a web project is refused, in one plain sentence", plan.refused == A.NOT_ANDROID,
          plan.refused)

    name, task = fresh()
    plan = A.plan_template(name, "0" * 12)
    check("a task that is not there is refused", "gone" in plan.refused, plan.refused)

    plan = A.plan_template(name, task, title="It's mine")
    check("a title with a quote in it is refused (an Android string treats it as a "
          "delimiter)", "quote" in plan.refused, plan.refused)
    plan = A.plan_template(name, task, background="blue")
    check("a colour that is not #RRGGBB is refused", "#101828" in plan.refused, plan.refused)
    plan = A.plan_template(name, task, assets={"settings.gradle.kts": "x"})
    check("a model cannot supply a Gradle file",
          "not one of this project's files" in plan.refused, plan.refused)
    plan = A.plan_template(name, task, assets={"../../escape.js": "x"})
    check("a path hiding in an asset's name is refused, not resolved",
          "not one of this project's files" in plan.refused, plan.refused)
    plan = A.plan_template(name, task, assets={"app.js": "x" * (A.MAX_ASSET_BYTES + 1)})
    check("an enormous asset is refused", "larger than" in plan.refused, plan.refused)
    plan = A.plan_template(name, task, assets={"app.js": b"bytes"})
    check("a non-text asset is refused", "must be text" in plan.refused, plan.refused)

    tdir = written(name, task)
    plan = A.plan_template(name, task)
    check("a task that already has a project is refused, so nothing is overwritten",
          "already has an Android project" in plan.refused, plan.refused)
    check("... and its files are untouched", tdir.is_dir())


def t_the_wrapper_files_are_gradles_own():
    bat, jar = A.wrapper_files()
    client = REPO / "jarvis-client" / "gradle" / "wrapper" / "gradle-wrapper.jar"
    client_bat = REPO / "jarvis-client" / "gradlew.bat"
    check("the wrapper jar this repository ships is jarvis-client's, byte for byte",
          jar.is_file() and client.is_file() and jar.read_bytes() == client.read_bytes())
    check("... and so is gradlew.bat, once line endings are put aside: this repository "
          "stores text as LF, and the generated copy gets its CRLF back",
          bat.is_file() and client_bat.is_file()
          and bat.read_bytes().replace(b"\r\n", b"\n")
          == client_bat.read_bytes().replace(b"\r\n", b"\n"))
    src = bat.read_bytes().replace(b"\r\n", b"\n")
    check("gradlew.bat is Gradle's Apache-2.0 script, untouched (it still says so)",
          b"Apache-2.0" in src and len(src) > 1000, len(src))


# --------------------------------------------------------------------------
#   The build
# --------------------------------------------------------------------------


def t_the_build_command_is_exactly_the_documented_one():
    name, task = fresh()
    tdir = written(name, task)
    with FakeToolchain(_TMP / "tc-build"):
        plan = A.plan_build(name, task)
        check("a written project has a build plan", plan.refused == "", plan.refused)
        check("the command is gradlew.bat assembleDebug, and nothing else",
              plan.argv == [str(tdir / "gradlew.bat"), "assembleDebug"], plan.argv)
        check("it runs IN the task's copy", plan.cwd == tdir, (plan.cwd, tdir))
        check("the time limit is the module's", plan.seconds == A.BUILD_SECONDS)
        check("the APK it will make is named", plan.apk == tdir / A.APK_REL)
        says = plan.says
        check("the card shows the exact command", "gradlew.bat assembleDebug" in says, says)
        check("the card shows the exact folder", str(tdir) in says)
        check("the card says the FIRST build downloads Gradle and the plugin, and from "
              "where", "FIRST build" in says and "services.gradle.org" in says
              and "dl.google.com" in says)
        check("the card says nothing of the owner's is sent", "nothing of yours is sent" in says)
        check("the card says the install is a second card",
              "second card" in says)
        check("the install is not part of this card",
              "install -r" not in says and "adb" not in says)


def t_the_build_refuses_without_a_project_or_a_toolchain():
    name, task = fresh()
    plan = A.plan_build(name, task)
    check("no project yet: refused", plan.refused == A.NOT_TEMPLATE, plan.refused)
    tdir = written(name, task)
    saved = A.sdk_root
    A.sdk_root = lambda: None
    saved_java = A.java_home
    A.java_home = lambda: None
    # The Windows guard comes BEFORE the toolchain check in plan_build, so on a
    # Linux CI runner (the required `backend` job runs on Ubuntu) the refusal is
    # "Windows only" and this check never sees the SDK sentence. The module reads
    # WINDOWS at call time for exactly this; set it like sdk_root/java_home.
    saved_windows = A.WINDOWS
    A.WINDOWS = True
    try:
        plan = A.plan_build(name, task)
        check("no Android SDK: refused, and the sentence names what is missing",
              "Android SDK" in plan.refused and "ANDROID_HOME" in plan.refused, plan.refused)
        check("... and the command is empty, so nothing could run",
              plan.argv == [], plan.argv)
    finally:
        A.sdk_root, A.java_home, A.WINDOWS = saved, saved_java, saved_windows
    check("the task's copy was never touched by a refusal", tdir.is_dir())


def t_a_build_without_a_yes_runs_nothing():
    name, task = fresh()
    written(name, task)
    with FakeToolchain(_TMP / "tc-no"), Ran() as ran:
        plan = A.plan_build(name, task)
        r = A.run_build(plan, approved=False)
        check("no approval: the answer is 'not approved'",
              r.get("ok") is False and r.get("error") == "not approved", r)
        check("... and NOTHING was started", ran.calls == [], ran.calls)
        plan.refused = "no"
        r = A.run_build(plan, approved=True)
        check("a plan already refused never runs", r.get("ok") is False and ran.calls == [])
        plan.refused = ""
        plan.argv = ["cmd.exe", "/c", "anything"]
        r = A.run_build(plan, approved=True)
        check("a tampered command is refused, and nothing runs",
              r.get("ok") is False and "not the build command" in r.get("error", ""),
              r)
        check("... still nothing started", ran.calls == [])


def t_a_build_runs_the_command_in_the_task_copy():
    name, task = fresh()
    tdir = written(name, task)
    with FakeToolchain(_TMP / "tc-run"), Ran() as ran:
        plan = A.plan_build(name, task)
        r = A.run_build(plan, approved=True)
        check("the build reports success and the APK", r.get("ok") is True, r)
        check("exactly one command ran", len(ran.calls) == 1, ran.calls)
        call = ran.calls[0]
        check("the argv is the documented one, not a shell string",
              call["argv"] == [str(tdir / "gradlew.bat"), "assembleDebug"], call["argv"])
        check("the working directory is the task's copy", call["cwd"] == tdir)
        check("the build log is kept inside the task's copy (and is gitignored)",
              (tdir / A.BUILD_LOG_REL).is_file()
              and ".gradle/" in W.GITIGNORE and "build/" in W.GITIGNORE)
        check("the APK really landed where the plan said",
              (tdir / A.APK_REL).is_file() and r["bytes"] > 0, r)


def t_a_failed_or_slow_build_says_so():
    name, task = fresh()
    written(name, task)
    with FakeToolchain(_TMP / "tc-fail"), Ran(code=1, make_apk=False):
        plan = A.plan_build(name, task)
        r = A.run_build(plan, approved=True)
        check("a failed build is a failure, not a crash", r.get("ok") is False, r)
        check("... and it says the exit code", "exit code 1" in r.get("error", ""), r)
        check("... and gives the END of Gradle's own words", "BUILD SUCCESSFUL" in r["log"])
    with FakeToolchain(_TMP / "tc-slow"), Ran(seconds_hit=True):
        plan = A.plan_build(name, task)
        r = A.run_build(plan, approved=True)
        check("a build past the time limit is stopped and says so",
              r.get("ok") is False and r.get("why") == "timed_out", r)
        check("... naming the limit in minutes",
              "minutes" in r.get("error", ""), r)
    name2, task2 = fresh()
    written(name2, task2)
    with FakeToolchain(_TMP / "tc-noapk"), Ran(code=0, make_apk=False):
        plan = A.plan_build(name2, task2)
        r = A.run_build(plan, approved=True)
        check("exit 0 with no APK is NOT a success", r.get("ok") is False, r)


def t_no_secret_reaches_gradle():
    name, task = fresh()
    written(name, task)
    os.environ["HUD_TOKEN"] = "secret-hud-token"
    os.environ["JARVIS_TOKEN"] = "secret-jarvis-token"
    os.environ["SOME_API_KEY"] = "secret-key"
    os.environ["DB_PASSWORD"] = "secret-password"
    try:
        with FakeToolchain(_TMP / "tc-env"), Ran() as ran:
            plan = A.plan_build(name, task)
            A.run_build(plan, approved=True)
            env = ran.calls[0]["env"]
            for name_ in ("HUD_TOKEN", "JARVIS_TOKEN", "SOME_API_KEY", "DB_PASSWORD"):
                check(f"{name_} is NOT in the build's environment", name_ not in env)
            check("... and no value of one leaked under another name",
                  not any("secret-" in str(v) for v in env.values()))
            check("ANDROID_HOME points at the SDK that was found",
                  env.get("ANDROID_HOME") == str(A.sdk_root()))
            check("JAVA_HOME points at the JDK that was found",
                  env.get("JAVA_HOME") == str(A.java_home()))
            check("the daemon is off, so no Gradle process outlives the card",
                  "daemon=false" in env.get("GRADLE_OPTS", ""), env.get("GRADLE_OPTS"))
            check("telemetry is off for the build too",
                  env.get("DO_NOT_TRACK") == "1")
    finally:
        for name_ in ("HUD_TOKEN", "JARVIS_TOKEN", "SOME_API_KEY", "DB_PASSWORD"):
            os.environ.pop(name_, None)
    src = (HERE / "jarvis_android_builder.py").read_text(encoding="utf-8")
    check("the module builds its environment from jarvis_child_env, not os.environ",
          "jarvis_child_env.inherited()" in src and "os.environ.copy()" not in src)


# --------------------------------------------------------------------------
#   The install
# --------------------------------------------------------------------------


def t_the_install_command_is_exactly_install_r():
    name, task = fresh()
    tdir = written(name, task)
    with FakeToolchain(_TMP / "tc-adb"):
        plan = A.plan_install(name, task)
        check("nothing to install before a build", plan.refused == A.BUILD_FIRST, plan.refused)
        apk = tdir / A.APK_REL
        apk.parent.mkdir(parents=True, exist_ok=True)
        apk.write_bytes(b"PK\x03\x04" + b"y" * 32)
        plan = A.plan_install(name, task)
        check("after a build there is a plan", plan.refused == "", plan.refused)
        adb = A.adb_path()
        check("the command is <full path to adb> install -r <the apk>, and nothing else",
              plan.argv == [str(adb), "install", "-r", str(apk)], plan.argv)
        check("... adb is called by its full path, never by name",
              os.path.isabs(plan.argv[0]) and plan.argv[0].endswith("adb.exe"), plan.argv[0])
        says = plan.says
        check("the card says it is a SIDELOAD and never the Play Store",
              "SIDELOAD" in says and "Play Store" in says)
        check("... names the file and its size", str(apk) in says and "KB" in says)
        check("... and says Jarvis runs no other adb command",
              "no other adb command" in says)


def t_the_install_refuses_files_that_are_not_the_apk():
    name, task = fresh()
    tdir = written(name, task)
    with FakeToolchain(_TMP / "tc-adb2") as have, Ran() as ran:
        plan = A.plan_install(name, task)
        r = A.run_install(plan, approved=True)
        check("no APK: nothing runs", r.get("ok") is False and ran.calls == [], r)
        apk = tdir / A.APK_REL
        apk.parent.mkdir(parents=True, exist_ok=True)
        apk.write_bytes(b"")
        check("an EMPTY file is not an APK", A.apk_inside(tdir) is None)
        apk.write_bytes(b"PK\x03\x04" + b"z" * 16)
        check("a real file at the APK's own path is accepted",
              A.apk_inside(tdir) == apk)
        notapk = tdir / "build" / "notes.apk"
        notapk.parent.mkdir(parents=True, exist_ok=True)
        notapk.write_bytes(b"PK\x03\x04")
        check("... and the module never looks anywhere but that one path",
              A.APK_REL == "app/build/outputs/apk/debug/app-debug.apk")
        outside = _TMP / "elsewhere.apk"
        outside.write_bytes(b"PK\x03\x04" + b"q" * 8)
        plan = A.plan_install(name, task)
        check("... and the plan it builds carries the file inside the copy",
              plan.apk == apk, (plan.apk, apk))
        # Tamper: the plan claims a file outside the task's copy.
        plan.argv = A.install_command(A.adb_path(), outside)
        r = A.run_install(plan, approved=True)
        check("an APK outside the task's copy is refused, and nothing runs",
              r.get("ok") is False and "not the install command" in r.get("error", ""), r)
        plan = A.plan_install(name, task)
        plan.argv = [str(A.adb_path()), "shell", "rm", "-rf", "/sdcard"]
        r = A.run_install(plan, approved=True)
        check("an adb SHELL command is refused", r.get("ok") is False, r)
        check("... and none of the three attempts started a program", ran.calls == [],
              ran.calls)


def t_install_runs_only_install_r():
    name, task = fresh()
    tdir = written(name, task)
    apk = tdir / A.APK_REL
    apk.parent.mkdir(parents=True, exist_ok=True)
    apk.write_bytes(b"PK\x03\x04" + b"w" * 48)
    with FakeToolchain(_TMP / "tc-adb3"), Ran() as ran:
        plan = A.plan_install(name, task)
        r = A.run_install(plan, approved=False)
        check("no yes, no install", r.get("ok") is False and ran.calls == [], r)
        r = A.run_install(plan, approved=True)
        check("a yes installs", r.get("ok") is True, r)
        call = ran.calls[0]
        check("exactly four arguments: adb, install, -r, the file",
              len(call["argv"]) == 4 and call["argv"][1:3] == ["install", "-r"],
              call["argv"])
        check("... in the task's copy", call["cwd"] == tdir)
        check("... with the same allowlisted environment as the build",
              "HUD_TOKEN" not in call["env"] and "ANDROID_HOME" in call["env"])
        check("... and the install's own time limit",
              call["seconds"] == A.INSTALL_SECONDS)
    src = (HERE / "jarvis_android_builder.py").read_text(encoding="utf-8")
    for forbidden in ('"shell"', '"uninstall"', '"-s"', '"exec-out"', '"push"',
                      '"pull"', "subprocess.Popen", "os.system", "shell=True"):
        check(f"no second adb door in the module: {forbidden}", forbidden not in src)


# --------------------------------------------------------------------------
#   The cards
# --------------------------------------------------------------------------


def t_the_build_card():
    A._reset_for_tests()
    name, task = fresh()
    written(name, task)
    gate = Gate()
    with FakeToolchain(_TMP / "tc-card"), Ran() as ran:
        pid = "p1"
        store = types.SimpleNamespace(app_of=lambda _pid: {"app": name, "name": "App"})
        code, body = A.handle_post(
            f"/api/projects/{pid}/app/tasks/{task}/android/build", {}, here=True,
            store=store, gate=gate, tier_of=lambda a: _TIER.get(a, "ask"),
            spawn=now_spawn)
        check("a build asks ONE card, at tier ask", code == 202 and body["waiting"] is True,
              (code, body))
        check("... for the build action",
              len(gate.calls) == 1 and gate.calls[0][0] == A.BUILD_ACTION, gate.calls)
        detail, text = gate.calls[0][1], gate.calls[0][2]
        check("the card names the exact command",
              detail["command"].endswith("gradlew.bat assembleDebug"), detail)
        check("... the exact folder", detail["cwd"] == str(W.task_dir(name, task)), detail)
        check("... and says it stays on this PC", detail["leaves_this_pc"] is False)
        check("the card's words are the plan's", text == A.plan_build(name, task).says or
              "gradlew.bat assembleDebug" in text)
        check("the yes ran the documented command exactly once",
              len(ran.calls) == 1 and ran.calls[0]["argv"][1] == A.GRADLE_TASK, ran.calls)
        code, body = A.handle_get(f"/api/projects/{pid}/app/tasks/{task}/android",
                                  store=store)
        check("the status then says it was built and shows the APK",
              code == 200 and body["apk"]["bytes"] > 0
              and body["last"]["outcome"] == "built", body.get("last"))


def t_the_install_card():
    A._reset_for_tests()
    name, task = fresh()
    tdir = written(name, task)
    apk = tdir / A.APK_REL
    apk.parent.mkdir(parents=True, exist_ok=True)
    apk.write_bytes(b"PK\x03\x04" + b"i" * 24)
    store = types.SimpleNamespace(app_of=lambda _pid: {"app": name, "name": "App"})
    gate = Gate()
    with FakeToolchain(_TMP / "tc-card2"), Ran() as ran:
        code, body = A.handle_post(
            f"/api/projects/p1/app/tasks/{task}/android/install", {}, here=True,
            store=store, gate=gate, tier_of=lambda a: _TIER.get(a, "ask"),
            spawn=now_spawn)
        check("an install asks ONE card, at tier ask", code == 202, (code, body))
        check("... for the install action",
              len(gate.calls) == 1 and gate.calls[0][0] == A.INSTALL_ACTION)
        check("the card names the exact adb command",
              " install -r " in gate.calls[0][1]["command"], gate.calls[0][1])
        check("... and the yes ran exactly it",
              len(ran.calls) == 1 and ran.calls[0]["argv"][1:3] == ["install", "-r"],
              ran.calls)
        code, body = A.handle_get(f"/api/projects/p1/app/tasks/{task}/android",
                                  store=store)
        check("the status says installed", body["last"]["outcome"] == "installed",
              body.get("last"))


def t_a_no_a_tier_change_and_a_stale_stream_all_leave_the_world_alone():
    A._reset_for_tests()
    name, task = fresh()
    written(name, task)
    store = types.SimpleNamespace(app_of=lambda _pid: {"app": name, "name": "App"})
    route = f"/api/projects/p1/app/tasks/{task}/android/build"
    for said, why in (
            (Said("denied", allowed=False), "a person said no"),
            (Said("timed_out", allowed=False), "the card timed out"),
            (Said("approved", tier="auto"), "a yes at a tier that is not ask"),
            (Said("approved", allowed=False), "an answer that did not allow it"),
            (Said(allowed=False, reason="the event stream is stale"),
             "a STALE event stream (rule 4)"),
            (Said("approved", allowed=True, tier="ask"), "a real yes")):
        A._reset_for_tests()
        with FakeToolchain(_TMP / "tc-answers"), Ran() as ran:
            code, body = A.handle_post(route, {}, here=True, store=store,
                                       gate=Gate(said), tier_of=lambda a: "ask",
                                       spawn=now_spawn)
            built = len(ran.calls) == 1
            if why == "a real yes":
                check(f"{why}: the command runs", code == 202 and built, (code, body))
            else:
                check(f"{why}: nothing runs", not built, ran.calls)
                if "stale" in why:
                    status = A.handle_get(
                        f"/api/projects/p1/app/tasks/{task}/android", store=store)[1]
                    check("... and the card records a refusal, not a build",
                          status["last"]["outcome"] == "refused", status.get("last"))


def t_the_tier_must_be_ask():
    A._reset_for_tests()
    name, task = fresh()
    tdir = written(name, task)
    apk = tdir / A.APK_REL
    apk.parent.mkdir(parents=True, exist_ok=True)
    apk.write_bytes(b"PK\x03\x04" + b"t" * 16)
    store = types.SimpleNamespace(app_of=lambda _pid: {"app": name, "name": "App"})
    gate = Gate()
    with FakeToolchain(_TMP / "tc-tier"), Ran() as ran:
        for action, leaf in ((A.BUILD_ACTION, "build"), (A.INSTALL_ACTION, "install")):
            route = f"/api/projects/p1/app/tasks/{task}/android/{leaf}"
            _TIER[action] = "auto"
            try:
                code, body = A.handle_post(route, {}, here=True, store=store, gate=gate,
                                           tier_of=lambda a: _TIER.get(a, "ask"),
                                           spawn=now_spawn)
                check(f"{action} at a looser tier on its own route: 503 naming the "
                      f"settings line, no card",
                      code == 503 and "jarvis-framework.toml" in body["error"]
                      and gate.calls == [], (code, body))
            finally:
                _TIER[action] = "ask"
        check("no command ran for either", ran.calls == [])


def t_a_card_already_waiting_and_one_that_goes_stale():
    A._reset_for_tests()
    name, task = fresh()
    written(name, task)
    store = types.SimpleNamespace(app_of=lambda _pid: {"app": name, "name": "App"})
    route = f"/api/projects/p1/app/tasks/{task}/android/build"
    held = Held()
    with FakeToolchain(_TMP / "tc-hold"):
        code1, _ = A.handle_post(route, {}, here=True, store=store, gate=Gate(),
                                 tier_of=lambda a: "ask", spawn=held)
        code2, body2 = A.handle_post(route, {}, here=True, store=store, gate=Gate(),
                                     tier_of=lambda a: "ask", spawn=held)
        check("a second card for the same task is refused with 409",
              code1 == 202 and code2 == 409 and body2["error"] == A.CARD_WAITING,
              (code1, code2, body2))
        check("... and only one piece of work is held", len(held.fns) == 1)
        A.withdraw(name, task)
        with Ran() as ran:
            for fn in held.fns:
                fn()
            check("a task thrown away while its card is up runs NOTHING",
                  ran.calls == [], ran.calls)


def t_a_gate_that_raises_is_a_refusal_not_a_crash():
    A._reset_for_tests()
    name, task = fresh()
    written(name, task)
    store = types.SimpleNamespace(app_of=lambda _pid: {"app": name, "name": "App"})
    with FakeToolchain(_TMP / "tc-raise"), Ran() as ran:
        code, body = A.handle_post(
            f"/api/projects/p1/app/tasks/{task}/android/build", {}, here=True, store=store,
            gate=Gate(raises=RuntimeError("gate is missing")), tier_of=lambda a: "ask",
            spawn=now_spawn)
        check("a gate that raises is a refusal, not a 500", code == 202, (code, body))
        check("... and nothing runs", ran.calls == [])
        status = A.handle_get(f"/api/projects/p1/app/tasks/{task}/android", store=store)[1]
        check("... and the recorded outcome says the gate failed",
              status["last"]["outcome"] == "refused"
              and "gate" in status["last"]["message"].lower(), status.get("last"))


# --------------------------------------------------------------------------
#   Routes: PC only, status, and the project a route must not find
# --------------------------------------------------------------------------


def t_build_and_install_are_pc_only():
    A._reset_for_tests()
    name, task = fresh()
    written(name, task)
    store = types.SimpleNamespace(app_of=lambda _pid: {"app": name, "name": "App"})
    gate = Gate()
    with FakeToolchain(_TMP / "tc-pc"), Ran() as ran:
        for leaf in ("template", "build", "install"):
            code, body = A.handle_post(f"/api/projects/p1/app/tasks/{task}/android/{leaf}",
                                       {}, here=False, store=store, gate=gate,
                                       tier_of=lambda a: "ask", spawn=now_spawn)
            check(f"{leaf} from the phone: 403 pc_only, before anything else",
                  code == 403 and body.get("pc_only") is True, (code, body))
        check("... no card was raised", gate.calls == [])
        check("... and nothing ran", ran.calls == [])


def t_the_routes_say_no_plainly():
    store = types.SimpleNamespace(app_of=lambda pid: (_ for _ in ()).throw(KeyError(pid)))
    code, body = A.handle_get("/api/projects/nope/app/tasks/" + "a" * 12 + "/android",
                              store=store)
    check("an unknown project is 404 with a sentence", code == 404
          and body["error"].endswith("."), (code, body))
    web = "webproject"
    W.create_project(web, "web", "Web")
    made = W.start_task(web, "T", source="empty")
    s2 = types.SimpleNamespace(app_of=lambda pid: {"app": web, "name": "Web"})
    code, body = A.handle_post(f"/api/projects/p1/app/tasks/{made['task']}/android/template",
                               {}, here=True, store=s2, gate=Gate(),
                               tier_of=lambda a: "ask", spawn=now_spawn)
    check("a web project's template is refused with a sentence, not a stack trace",
          code == 400 and body["error"].endswith("."), (code, body))
    A._reset_for_tests()
    name, task = fresh()
    with FakeToolchain(_TMP / "tc-plain"):
        code, body = A.handle_post(f"/api/projects/p1/app/tasks/{task}/android/template",
                                   {}, here=True,
                                   store=types.SimpleNamespace(
                                       app_of=lambda pid: {"app": name, "name": "App"}),
                                   gate=Gate(), tier_of=lambda a: "ask", spawn=now_spawn)
        check("the template route writes the project and answers with the status",
              code == 200 and body["status"]["template"] is True, (code, body))
        status = body["status"]
        check("the status names the toolchain it found",
              "sdk" in status["toolchain"] and "adb" in status["toolchain"])
        check("... and both next commands, so the owner can see what a card would run",
              status["build"]["command"].endswith("assembleDebug")
              and "install" in status["install"]["command"] or status["install"]["refused"])
        code, body = A.handle_post(f"/api/projects/p1/app/tasks/{task}/android/template",
                                   {}, here=True,
                                   store=types.SimpleNamespace(
                                       app_of=lambda pid: {"app": name, "name": "App"}),
                                   gate=Gate(), tier_of=lambda a: "ask", spawn=now_spawn)
        check("a second template write is refused, never a silent overwrite",
              code == 400 and "already" in body["error"], (code, body))
        code, body = A.handle_get("/api/projects/p1/app/tasks/" + "b" * 12 + "/android",
                                  store=types.SimpleNamespace(
                                      app_of=lambda pid: {"app": name, "name": "App"}))
        check("a task that is not there is 404", code == 404, (code, body))


def t_install_wraps_the_routes():
    """The one piece of wiring this suite can prove: install() wraps a
    Handler exactly as every other module's does, answers ITS routes, refuses
    on the server's own origin/token checks, and lets every other request
    through untouched.

    Each check gets a NEW class, because install() marks the do_GET/do_POST it
    wrapped and would (rightly) answer "already on" to a second call on the
    same one - which is itself one of the checks below."""
    A._reset_for_tests()
    name, task = fresh()
    written(name, task)

    def handler_class():
        class Fake:
            def __init__(self):
                self.path = ""
                self.sent = []
                self.body = b"{}"

            def _send(self, code, out):
                self.sent.append((code, out))
                return code

            def do_GET(self):
                self.sent.append(("original", None))

            def do_POST(self):
                self.sent.append(("original", None))

        return Fake

    def wrapped(cls, *, origin=True, token=True):
        return A.install(cls, origin_ok=lambda h: origin, token_ok=lambda h: token,
                         read_body=lambda h: h.body)

    saved = A._resolve
    A._resolve = lambda store, pid: (name, "App")
    try:
        Fake = handler_class()
        line = wrapped(Fake)
        check("install() returns a banner line a reader understands",
              isinstance(line, str) and "android" in line.lower(), line)
        check("installing the same module twice is harmless and says it is already on",
              "already on" in wrapped(Fake))
        got = Fake()
        got.path = f"/api/projects/p1/app/tasks/{task}/android"
        got.do_GET()
        check("a GET on the status route is answered by the module",
              got.sent and got.sent[-1][0] == 200 and got.sent[-1][1]["ok"] is True,
              got.sent[-1:])
        other = Fake()
        other.path = "/api/status"
        other.do_GET()
        check("every other route falls through to the original handler, untouched",
              other.sent == [("original", None)], other.sent)
        post = Fake()
        post.path = f"/api/projects/p1/app/tasks/{task}/android/build"
        post.do_POST()
        check("a POST is answered too - 403 pc_only here, because a fake Handler is "
              "not this PC",
              post.sent and post.sent[-1][0] == 403
              and post.sent[-1][1]["pc_only"] is True, post.sent[-1:])
        NoToken = handler_class()
        wrapped(NoToken, token=False)
        nt = NoToken()
        nt.path = f"/api/projects/p1/app/tasks/{task}/android"
        nt.do_GET()
        check("no token: 401 and the module answers nothing",
              nt.sent and nt.sent[-1][0] == 401, nt.sent[-1:])
        OtherOrigin = handler_class()
        wrapped(OtherOrigin, origin=False)
        oo = OtherOrigin()
        oo.path = f"/api/projects/p1/app/tasks/{task}/android"
        oo.do_GET()
        check("another origin: 403, before the token is even looked at",
              oo.sent and oo.sent[-1][0] == 403, oo.sent[-1:])
    finally:
        A._resolve = saved


# --------------------------------------------------------------------------
#   The wiring: the gate, the settings, the drop-in folder
# --------------------------------------------------------------------------


def t_the_gate_rows():
    gate = (REPO / "jarvis-backend" / "jarvis_gate.py").read_text(encoding="utf-8")
    # The build reaches the internet (a download), the install does not: the
    # two reaches are deliberately different, and the card says which.
    reach = {A.BUILD_ACTION: "outbound", A.INSTALL_ACTION: "local"}
    for action in (A.BUILD_ACTION, A.INSTALL_ACTION):
        row = [l for l in gate.split("\n") if l.startswith(f'    "{action}": (')]
        check(f"{action} has ONE row in the gate's risk table", len(row) == 1, row)
        check(f"... which says it cannot be undone (no) and reaches {reach[action]}",
              bool(row) and row[0].startswith(f'    "{action}": ("no", "{reach[action]}", '),
              row)
        check(f"... and is in the no-standing-rule list exactly once",
              gate.count(f'"{action}",  #') == 1,
              gate.count(f'"{action}",  #'))
        import jarvis_owner_check as OC
        check("so its card is RISKY: Windows Hello on the PC, the screen lock on the phone",
              OC.is_risky({"risk": {"classified": True, "reach": reach[action],
                                    "reversible": "no", "swipe_ok": False}}) is True)
        check("... and it is not a PC-only CARD: the phone may still approve it",
              action not in OC.PC_ONLY_ACTIONS)
    import jarvis_card_words as CW
    for action in (A.BUILD_ACTION, A.INSTALL_ACTION):
        check(f"{action} has plain card words",
              isinstance(CW.TITLES.get(action), str) and CW.TITLES.get(action), action)
    build_row = [l for l in gate.split("\n") if l.startswith(f'    "{A.BUILD_ACTION}": (')]
    check("the build's row names the three hosts a first build reaches, so the card can",
          bool(build_row) and "services.gradle.org" in build_row[0]
          and "dl.google.com" in build_row[0] and "repo.maven.apache.org" in build_row[0])
    check("... and says nothing of the owner's is sent",
          bool(build_row) and "nothing of yours is sent" in build_row[0])


def t_the_tier_lines():
    for path in (HERE / "rebuilt" / "jarvis-framework.toml",
                 REPO / "jarvis-backend" / "jarvis-framework.toml"):
        text = path.read_text(encoding="utf-8")
        where = "the template" if "rebuilt" in path.parts else "the published base"
        for action in (A.BUILD_ACTION, A.INSTALL_ACTION):
            check(f"{where}: {action} is set to ask in the settings file",
                  any(l.replace(" ", "") == f"{action}=\"ask\"" for l in text.split("\n")),
                  action)


def t_the_drop_in_folder():
    folder = REPO / "plugins" / "ready" / "android-builder"
    manifest = folder / "plugin.json"
    check("the drop-in folder exists", folder.is_dir())
    data = json.loads(manifest.read_text(encoding="utf-8"))
    check("its plugin.json names this module and the handler install",
          data.get("module") == "jarvis_android_builder" and data.get("install") == "handler",
          data)
    check("... with a summary a reader can understand",
          isinstance(data.get("summary"), str) and len(data["summary"]) > 40, data)
    registry = json.loads((REPO / "plugins" / "registry.json").read_text(encoding="utf-8"))
    rows = [f for f in registry.get("folders", []) if f.get("name") == "android-builder"]
    check("the generated catalogue lists it, so check_plugins.py can account for the "
          "folder", len(rows) == 1, registry.get("folder_count"))
    check("... and README.md beside it says what it does and how to take it out",
          (folder / "README.md").is_file()
          and "Taking it out" in (folder / "README.md").read_text(encoding="utf-8"))
    check("this feature adds NO patch, so it needs no DELTA_TABLE entry and cannot block "
          "a deploy",
          not (HERE / "android-app-builder.patch").exists()
          and "jarvis_android_builder" not in (REPO / "tools" / "reconcile_live_backend.py")
          .read_text(encoding="utf-8"))


def t_the_lists_that_must_carry_it():
    where = (HERE / "_where.py").read_text(encoding="utf-8")
    check("the module is in backend/_where.py's SHIPPED list",
          '"jarvis_android_builder.py"' in where)
    base_where = (REPO / "jarvis-backend" / "_where.py").read_text(encoding="utf-8")
    check("... and in the published base's, which is derived from it",
          '"jarvis_android_builder.py"' in base_where)
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("apply-patches.ps1 copies the module in", "'jarvis_android_builder.py'" in ps1)
    check("... and the two Gradle wrapper files it needs",
          "'jarvis-android-wrapper.jar'" in ps1
          and "'jarvis-android-gradlew.bat'" in ps1)
    gen = (REPO / "tools" / "gen_base_from_backend.py").read_text(encoding="utf-8")
    check("the published base carries the wrapper jar and script as BYTES",
          gen.count("jarvis-android-wrapper.jar") >= 1
          and gen.count("jarvis-android-gradlew.bat") >= 1)
    check("the twin module is byte-identical to this one (the base is published from it)",
          (REPO / "jarvis-backend" / "jarvis_android_builder.py").is_file()
          and (REPO / "jarvis-backend" / "jarvis_android_builder.py").read_bytes()
          == (HERE / "jarvis_android_builder.py").read_bytes())


def t_the_source_has_no_extra_door():
    src = (HERE / "jarvis_android_builder.py").read_text(encoding="utf-8")
    for word in ("import urllib", "import http", "import requests", "import socket",
                 "ask_model", "ollama", "cap sync"):
        check(f"the module does not do this: {word}", word not in src)
    check("every path it writes is one of its own constants or the closed asset list",
          "ASSETS" in src and "template_paths" in src)
    check("nothing in this feature tried to open a network connection", _NET == [], _NET[:3])


def t_the_audit_log_holds_counts_only():
    detail = [d for _e, d in _AUDIT if d]
    bad = []
    for d in detail:
        for key, value in (d or {}).items():
            if key in ("path", "file", "apk", "command", "title", "package", "log"):
                bad.append(d)
    check("the audit log never carries a path, a command or a line of a page", bad == [], bad)


def main():
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        socket.socket.connect = _real_connect
        _rmtree(_TMP)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
