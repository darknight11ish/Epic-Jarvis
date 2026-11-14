"""test_android_builder_native.py - a real app with its own screens, written
by the model as DATA and drawn by one fixed Kotlin activity
(jarvis_android_builder.py, the native-screens kind, 2026-11-14).

    python3 backend/test_android_builder_native.py

THE OWNER'S ASK. The Android builder could already make one kind of app: a
WebView showing a page the model wrote. They asked for a real app with its own
screens. This suite proves the second kind without ever compiling anything
(the compile is measured by hand on the PC, never in CI):

  - THE SPEC IS DATA. A valid `app.json` in the task's copy builds the fixed
    project: the Gradle files, the permission-free manifest, ONE Kotlin file,
    and the VALIDATED spec in `assets/app.json`. The task's own files choose
    the kind, so a task without `app.json` is still the WebView app.
  - THE LIMITS. At most 8 screens, 40 list items, 6 form fields, 4 buttons per
    screen, 400 characters in any string, 40 in a title or label, ids matching
    `[a-z][a-z0-9_-]{0,23}`, every `open` naming a screen that exists, a start
    that exists, and no duplicate ids. Each refusal is in plain words and
    names the offending value - and no project file is written.
  - UNKNOWN KEYS ARE REFUSED, never ignored: at the root, on a screen, on an
    item, on a field, on a button and in an action.
  - NOTHING CAN BECOME CODE OR A PERMISSION. The one Kotlin file is the
    module's own constant, byte for byte, whatever the spec's text says; the
    manifest declares no permission even when a paragraph names one; the spec
    has no path and no key that reaches Gradle, the manifest or a command.
  - THE CARDS. The build card names the REAL app name and how many screens it
    will build, and a broken spec is refused BEFORE a card is raised. The
    install card names the same app.
  - THE WEBVIEW KIND IS UNCHANGED: the same 15 paths, the same activity text,
    the same refusals, no `assets/app.json`.

No pytest, no network, no model, no Gradle, no adb.
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
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_android_builder.py", "jarvis_app_workspace.py",
                "jarvis_projects.py", "jarvis_child_env.py")

if shutil.which("git") is None:
    print("SKIP  git is not installed here - these tests run real git")
    sys.exit(0)

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-android-native-"))
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
    raise OSError("test_android_builder_native.py: no network")


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
        self.request_id = "req-test"


class Gate:
    """A fake approval gate: records every card, answers as told."""

    def __init__(self, answer=None):
        self.calls = []
        self.answer = answer if answer is not None else Said()

    def __call__(self, action, detail, prompt):
        self.calls.append((action, detail, prompt))
        return self.answer


def now_spawn(fn):
    fn()


def _rmtree(path):
    for dirpath, dirnames, filenames in os.walk(path):
        for name in list(dirnames) + list(filenames):
            try:
                os.chmod(os.path.join(dirpath, name), 0o700)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


_N = [0]


def fresh() -> tuple:
    """A new app called `nappN`, of kind "android", with one empty task."""
    _N[0] += 1
    name = f"napp{_N[0]}"
    W.create_project(name, "android", f"Native {_N[0]}")
    made = W.start_task(name, "Build it", source="empty")
    return name, made["task"]


def good_spec() -> dict:
    """A realistic spec: one text screen, one list, one form, all three kinds
    of content, both kinds of button, and every key the format allows."""
    return {
        "name": "My Notes",
        "package_tail": "my_notes",
        "bg": "#101828",
        "accent": "#7cc4ff",
        "start": "home",
        "screens": [
            {"id": "home", "title": "Home", "kind": "text",
             "body": ["A short line about today.", "And a second paragraph."],
             "buttons": [
                 {"label": "To the list", "action": {"do": "open", "screen": "todo"}},
                 {"label": "Say hello", "action": {"do": "show", "text": "Hello."}}]},
            {"id": "todo", "title": "To do", "kind": "list",
             "items": [{"title": "Milk", "detail": "Two bottles"},
                       {"title": "Bread", "detail": "The seeded one"}],
             "buttons": [{"label": "Back", "action": {"do": "open", "screen": "home"}}]},
            {"id": "capture", "title": "Capture", "kind": "form",
             "fields": [{"key": "note", "label": "The note"},
                        {"key": "who", "label": "For whom"}],
             "save_label": "Save it",
             "buttons": [{"label": "Back", "action": {"do": "open", "screen": "home"}}]},
        ],
    }


def put_spec(name, task, data=None, raw=None):
    """The model writes ONE file into the task's copy: `app.json`."""
    text = raw if raw is not None else json.dumps(
        good_spec() if data is None else data, indent=2)
    W.apply_change(name, task, [("write", A.SPEC_FILE, text + "\n")], "Write the screens")
    return text + "\n"


def built(data=None) -> tuple:
    """A task whose app.json is valid and whose project has been written."""
    name, task = fresh()
    put_spec(name, task, data)
    plan = A.plan_template(name, task)
    assert not plan.refused, plan.refused
    A.write_template(plan)
    return name, task, W.task_dir(name, task)


def refused(data=None, raw=None):
    """(the refused plan, whether any project file was written)."""
    name, task = fresh()
    put_spec(name, task, data, raw)
    plan = A.plan_template(name, task)
    wrote = (W.task_dir(name, task) / "settings.gradle.kts").exists()
    return plan, wrote


def limit_case(change, must_say, name):
    """One limit: change the good spec, refuse it, and check the plain words
    name the offending value. Also proves nothing was written."""
    data = good_spec()
    change(data)
    plan, wrote = refused(data)
    said = plan.refused
    check(f"{name}: refused", bool(said), said or "no refusal")
    check(f"{name}: the words name the offending value",
          all(word in said for word in must_say), said)
    check(f"{name}: no project file was written", not wrote)


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


def _read(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
#   A valid spec: the fixed project, the fixed Kotlin, the validated data
# --------------------------------------------------------------------------


def t_a_valid_spec_builds_a_native_app():
    data = good_spec()
    name, task = fresh()
    put_spec(name, task, data)
    tdir = W.task_dir(name, task)
    plan = A.plan_template(name, task)
    check("a valid spec is accepted", plan.refused == "", plan.refused)
    check("... the task's app.json chooses the native-screens kind",
          plan.kind == A.NATIVE, plan.kind)
    check("... and the plan names the app from the spec", plan.title == "My Notes", plan.title)
    check("... with the spec's own package tail, not the folder name",
          plan.package == "com.jarvis.made.my_notes", plan.package)
    check("... and counts the screens", plan.screens == 3, plan.screens)
    done = A.write_template(plan)
    check("it reports every file it wrote",
          done["files"] == len(A.template_paths(name, package=plan.package, native=True)),
          (done, len(A.template_paths(name, package=plan.package, native=True))))
    check("... and says which kind it wrote", done["kind"] == A.NATIVE and
          done["screens"] == 3, done)
    for rel in A.template_paths(name, package=plan.package, native=True):
        check(f"written: {rel}", (tdir / rel).is_file())
    asset = tdir / A.SPEC_ASSET
    check("the spec ships inside the app's assets", asset.is_file())
    shipped = json.loads(_read(asset))
    check("... as the VALIDATED data, not the model's raw text",
          shipped["name"] == "My Notes" and len(shipped["screens"]) == 3, shipped.get("name"))
    check("... and every string in it is one the checks allow",
          all(len(s) <= A.MAX_TEXT for s in
              [shipped["name"], shipped["start"]]
              + [p for s in shipped["screens"] for p in (s.get("body") or [])]))
    activity_path = tdir / "app/src/main/java/com/jarvis/made/my_notes/MainActivity.kt"
    activity = _read(activity_path)
    check("the one Kotlin file is the module's fixed screens activity",
          activity == A._fill(A._MAIN_ACTIVITY_SCREENS, package="com.jarvis.made.my_notes"))
    check("... which reads the spec from assets/app.json",
          'assets.open("app.json")' in activity and "org.json.JSONObject" in activity)
    check("... and builds with ordinary Android views",
          all(word in activity for word in
              ("ScrollView", "LinearLayout", "TextView", "EditText", "Button")))
    check("... saving a form to the phone's own SharedPreferences and nowhere else",
          "getSharedPreferences" in activity and "Saved on this phone." in activity)
    check("... showing a button's short line in a Toast",
          "Toast.makeText" in activity)
    check("... and there is NO WebView, Compose or library in it",
          not any(word in activity for word in
                  ("WebView(", "androidx", "import android.webkit", "setJavaScriptEnabled")))
    check("... nor any permission or internet call",
          not any(word in activity for word in
                  ("android.permission", "uses-permission", "INTERNET", "http://",
                   "https://", "java.net.Socket")))
    kt = [p for p in tdir.rglob("*.kt")]
    check("the whole app is ONE Kotlin file - the model wrote none",
          len(kt) == 1, [str(p) for p in kt])
    check("the native app has no web page in its assets",
          not any((tdir / A.ASSET_DIR / a).exists() for a in A.ASSETS))
    manifest = _read(tdir / "app/src/main/AndroidManifest.xml")
    check("the manifest declares no permission at all",
          "<uses-permission" not in manifest and "android.permission" not in manifest)
    strings = _read(tdir / "app/src/main/res/values/strings.xml")
    check("the phone shows the spec's name for the app",
          '<string name="app_name">My Notes</string>' in strings, strings)
    colours = _read(tdir / "app/src/main/res/values/colors.xml")
    check("... and the two colours the spec named",
          '<color name="jarvis_background">#101828</color>' in colours
          and '<color name="jarvis_accent">#7cc4ff</color>' in colours, colours)
    gradle = _read(tdir / "app/build.gradle.kts")
    check("the module's build file carries the spec's package and the pinned SDK levels",
          'namespace = "com.jarvis.made.my_notes"' in gradle
          and f"compileSdk = {A.COMPILE_SDK}" in gradle and f"minSdk = {A.MIN_SDK}" in gradle,
          gradle)
    check("the Gradle task and the APK path are still the module's constants",
          A.GRADLE_TASK == "assembleDebug"
          and A.APK_REL == "app/build/outputs/apk/debug/app-debug.apk")
    props = _read(tdir / "gradle/wrapper/gradle-wrapper.properties")
    check("the wrapper is the same pinned Gradle and SHA-256 as the WebView kind",
          f"gradle-{A.GRADLE_VERSION}-bin.zip" in props and A.GRADLE_DIST_SHA256 in props)
    status = A.status(name, task)
    check("the status says native and how many screens",
          status["kind"] == A.NATIVE and status["screens"] == 3
          and status["title"] == "My Notes", status)
    check("... with no spec contents in it",
          "A short line about today." not in json.dumps(status))


def t_the_model_writes_data_never_code():
    data = good_spec()
    hostile = "fun main() { } </LinearLayout> ../../escape"
    data["screens"][0]["body"].append(hostile)
    data["screens"][0]["title"] = "Screens!"
    name, task, tdir = built(data)
    activity = _read(tdir / "app/src/main/java/com/jarvis/made/my_notes/MainActivity.kt")
    check("spec text does not reach the Kotlin file",
          hostile not in activity and "Screens!" not in activity)
    check("... the activity is still exactly the fixed template",
          activity == A._fill(A._MAIN_ACTIVITY_SCREENS, package="com.jarvis.made.my_notes"))
    asset = _read(tdir / A.SPEC_ASSET)
    check("... the hostile words are only DATA, in the spec's own JSON",
          hostile in asset and "Screens!" in asset)
    check("... and the app's files are only the fixed ones plus the model's own spec",
          (tdir / "app" / "src" / "main" / "res" / "values" / "themes.xml").is_file()
          and (tdir / "app" / "build.gradle.kts").is_file())
    check("nothing was written outside the task's copy",
          not (W.project_dir(name) / "settings.gradle.kts").exists())


# --------------------------------------------------------------------------
#   The hard limits: refused, in plain words, naming the offending value
# --------------------------------------------------------------------------


def t_every_limit_is_refused_in_plain_words():
    def nine_screens(spec):
        spec["screens"] = [{"id": f"s{i}", "title": "One", "kind": "text", "body": ["x"]}
                           for i in range(9)]

    def forty_one_items(spec):
        spec["screens"][1]["items"] = [{"title": "T", "detail": "D"}] * 41

    def seven_fields(spec):
        spec["screens"][2]["fields"] = [{"key": f"f{i}", "label": "L"} for i in range(7)]

    def five_buttons(spec):
        spec["screens"][0]["buttons"] = [
            {"label": "B", "action": {"do": "show", "text": "x"}}] * 5

    def long_detail(spec):
        spec["screens"][1]["items"][0]["detail"] = "d" * 401

    def long_title(spec):
        spec["screens"][0]["title"] = "t" * 41

    def long_button_label(spec):
        spec["screens"][0]["buttons"][0]["label"] = "b" * 41

    def long_field_label(spec):
        spec["screens"][2]["fields"][0]["label"] = "l" * 41

    def long_save_label(spec):
        spec["screens"][2]["save_label"] = "s" * 41

    def long_paragraph(spec):
        spec["screens"][0]["body"].append("p" * 401)

    def long_show_text(spec):
        spec["screens"][0]["buttons"][1]["action"]["text"] = "x" * 401

    def long_name(spec):
        spec["name"] = "N" * 41

    def upper_id(spec):
        spec["screens"][0]["id"] = "Home"

    def long_id(spec):
        spec["screens"][0]["id"] = "a" + "b" * 24

    def dash_id(spec):
        spec["screens"][0]["id"] = "-home"

    def duplicate_id(spec):
        spec["screens"][1]["id"] = "home"

    def missing_open(spec):
        spec["screens"][0]["buttons"][0]["action"]["screen"] = "nope"

    def missing_start(spec):
        spec["start"] = "welcome"

    def bad_tail(spec):
        spec["package_tail"] = "My App"

    def bad_bg(spec):
        spec["bg"] = "blue"

    def bad_accent(spec):
        spec["accent"] = "#12345"

    def quoted_name(spec):
        spec["name"] = "It's mine"

    def no_screens(spec):
        spec["screens"] = []

    def bad_kind(spec):
        spec["screens"][0]["kind"] = "video"

    def unknown_root(spec):
        spec["permissions"] = ["android.permission.INTERNET"]

    def unknown_screen(spec):
        spec["screens"][0]["footer"] = "x"

    def unknown_item(spec):
        spec["screens"][1]["items"][0]["icon"] = "x"

    def unknown_field(spec):
        spec["screens"][2]["fields"][0]["type"] = "password"

    def unknown_button(spec):
        spec["screens"][0]["buttons"][0]["style"] = "big"

    def unknown_action(spec):
        spec["screens"][0]["buttons"][1]["action"]["url"] = "https://example.com"

    def unknown_do(spec):
        spec["screens"][0]["buttons"][1]["action"]["do"] = "browse"

    def text_with_items(spec):
        spec["screens"][0]["items"] = []

    def list_without_items(spec):
        del spec["screens"][1]["items"]

    def form_without_save(spec):
        del spec["screens"][2]["save_label"]

    def body_not_list(spec):
        spec["screens"][0]["body"] = "one line"

    def control_char(spec):
        spec["screens"][0]["body"].append("a\x00b")

    limit_case(nine_screens, ("9", "8", "screens"), "nine screens")
    limit_case(forty_one_items, ("41", "40", "items"), "41 list items")
    limit_case(seven_fields, ("7", "6", "fields"), "7 form fields")
    limit_case(five_buttons, ("5", "4", "buttons"), "5 buttons on one screen")
    limit_case(long_detail, ("401", "400"), "a 401-character detail")
    limit_case(long_title, ("41", "40", "title"), "a 41-character screen title")
    limit_case(long_button_label, ("41", "40"), "a 41-character button label")
    limit_case(long_field_label, ("41", "40"), "a 41-character field label")
    limit_case(long_save_label, ("41", "40"), "a 41-character save_label")
    limit_case(long_paragraph, ("401", "400"), "a 401-character paragraph")
    limit_case(long_show_text, ("401", "400"), "a 401-character show text")
    limit_case(long_name, ("name",), "a 41-character app name")
    limit_case(upper_id, ("Home", "small letters"), "an id with a capital")
    limit_case(long_id, ("a" + "b" * 24, "up to 24"), "an id over 24 characters")
    limit_case(dash_id, ("-home",), "an id starting with a dash")
    limit_case(duplicate_id, ("home", "two screens"), "two screens with one id")
    limit_case(missing_open, ("nope", "home"), "open to a screen that does not exist")
    limit_case(missing_start, ("welcome",), "a start screen that does not exist")
    limit_case(bad_tail, ("My App", "package ending"), "a package tail with a space")
    limit_case(bad_bg, ("bg", "colour"), "a bg that is not #RRGGBB")
    limit_case(bad_accent, ("accent", "colour"), "an accent that is not #RRGGBB")
    limit_case(quoted_name, ("It's mine", "quote"), "an app name with a quote")
    limit_case(no_screens, ("at least one screen",), "no screens at all")
    limit_case(bad_kind, ("video", "kind"), "a kind that is not text, list or form")
    limit_case(unknown_root, ("permissions",), "an unknown root key")
    limit_case(unknown_screen, ("footer",), "an unknown screen key")
    limit_case(unknown_item, ("icon",), "an unknown item key")
    limit_case(unknown_field, ("type",), "an unknown field key")
    limit_case(unknown_button, ("style",), "an unknown button key")
    limit_case(unknown_action, ("url",), "an unknown action key")
    limit_case(unknown_do, ("browse", "open"), "an action that is neither open nor show")
    limit_case(text_with_items, ("items",), "items on a text screen")
    limit_case(list_without_items, ("items",), "a list screen with no items")
    limit_case(form_without_save, ("Save button",), "a form with no save label")
    limit_case(body_not_list, ("body",), "a body that is not a list")
    limit_case(control_char, ("control character",), "a control character")

    # The file itself: not JSON, not an object, not UTF-8, and too big.
    plan, wrote = refused(raw="{not json")
    check("a spec that is not JSON is refused, naming the line",
          "not valid JSON" in plan.refused and "line" in plan.refused and not wrote,
          plan.refused)
    plan, wrote = refused(raw="[1, 2, 3]")
    check("a spec that is a list, not one object, is refused",
          "one JSON object" in plan.refused and not wrote, plan.refused)
    name, task = fresh()
    bad = W.task_dir(name, task) / A.SPEC_FILE
    bad.write_bytes(b"\xff\xfe\x00")
    plan = A.plan_template(name, task)
    check("a spec that is not UTF-8 is refused",
          "UTF-8" in plan.refused and not (W.task_dir(name, task) /
                                           "settings.gradle.kts").exists(), plan.refused)
    name, task = fresh()
    big = W.task_dir(name, task) / A.SPEC_FILE
    big.write_text(json.dumps(good_spec()) + " " * (A.MAX_SPEC_BYTES + 1), encoding="utf-8")
    plan = A.plan_template(name, task)
    check("a spec larger than the limit is refused before it is parsed",
          "larger than" in plan.refused
          and not (W.task_dir(name, task) / "settings.gradle.kts").exists(), plan.refused)


def t_unknown_keys_are_always_refused():
    """A key the fixed activity would ignore is refused, never silently
    dropped: the owner is told which key, and none of the spec is built."""
    cases = []
    data = good_spec()
    data["colour"] = "#ffffff"
    cases.append(("root", data))
    data = good_spec()
    data["screens"][0]["image"] = "x"
    cases.append(("screen", data))
    data = good_spec()
    data["screens"][1]["items"][0]["when"] = "today"
    cases.append(("item", data))
    data = good_spec()
    data["screens"][2]["fields"][0]["hint"] = "type here"
    cases.append(("field", data))
    data = good_spec()
    data["screens"][0]["buttons"][0]["colour"] = "red"
    cases.append(("button", data))
    data = good_spec()
    data["screens"][0]["buttons"][1]["action"]["open"] = "todo"
    cases.append(("action", data))
    for where, spec in cases:
        plan, wrote = refused(spec)
        key = {"root": "colour", "screen": "image", "item": "when", "field": "hint",
               "button": "colour", "action": "open"}[where]
        check(f"an unknown key on the {where} is refused and named",
              key in plan.refused and "does not use" in plan.refused, plan.refused)
        check(f"... and nothing was written ({where})", not wrote)


# --------------------------------------------------------------------------
#   Nothing the spec says can add a permission or reach a command
# --------------------------------------------------------------------------


def t_no_permission_can_reach_the_manifest():
    data = good_spec()
    data["screens"][0]["body"].append(
        '<uses-permission android:name="android.permission.INTERNET"/>')
    data["screens"][0]["title"] = "INTERNET"
    name, task, tdir = built(data)
    manifest = _read(tdir / "app/src/main/AndroidManifest.xml")
    check("a paragraph that names a permission cannot put one in the manifest",
          "<uses-permission" not in manifest and "android.permission" not in manifest,
          manifest)
    check("... and the app still declares NO permission at all",
          "usesCleartextTraffic=\"false\"" in manifest)
    strings = _read(tdir / "app/src/main/res/values/strings.xml")
    check("... and the app's label is still plain text from the spec's name",
          '<string name="app_name">My Notes</string>' in strings
          and "<uses-permission" not in strings, strings)
    plan, wrote = refused({**good_spec(), "name": "A < B"})
    check("... a name carrying XML markup is refused before anything is built",
          "name" in plan.refused and not wrote, plan.refused)
    check("... the words are only data in the spec's JSON",
          "uses-permission" in _read(tdir / A.SPEC_ASSET))
    plan, wrote = refused({**good_spec(), "permissions": ["android.permission.INTERNET"]})
    check("a spec that ASKS for a permission is refused before anything is built",
          "permissions" in plan.refused and not wrote, plan.refused)
    plan, wrote = refused({**good_spec(), "manifest": "<uses-permission/>"})
    check("... and so is one that asks for a manifest",
          "manifest" in plan.refused and not wrote, plan.refused)


def t_no_new_door_in_the_module():
    src = _read(HERE / "jarvis_android_builder.py")
    for word in ("import urllib", "import http", "import requests", "import socket",
                 "ask_model", "ollama", "subprocess.Popen", "shell=True",
                 "import compose", "androidx.compose"):
        check(f"the module does not do this: {word}", word not in src)
    check("the one Gradle task is still the constant",
          A.GRADLE_TASK == "assembleDebug"
          and A.build_command(Path("C:/x"))[-1] == "assembleDebug")
    check("the one install command is still adb install -r",
          A.install_command(Path("adb.exe"), Path("app.apk"))[1:] ==
          ["install", "-r", str(Path("app.apk"))])
    check("no permission string in the native activity",
          "android.permission" not in A._MAIN_ACTIVITY_SCREENS
          and "uses-permission" not in A._MAIN_ACTIVITY_SCREENS)
    check("the native activity has no WebView, Compose or library",
          not any(word in A._MAIN_ACTIVITY_SCREENS for word in
                  ("WebView(", "androidx", "import android.webkit",
                   "setJavaScriptEnabled")))
    check("nothing in this feature opened a network connection", _NET == [], _NET[:3])


# --------------------------------------------------------------------------
#   The cards: the real name, what will be built, and no card over a bad spec
# --------------------------------------------------------------------------


def t_the_build_card_names_the_app_and_what_will_be_built():
    A._reset_for_tests()
    name, task, tdir = built()
    with FakeToolchain(_TMP / "tc-build"):
        plan = A.plan_build(name, task)
        check("a native project has a build plan", plan.refused == "", plan.refused)
        check("the card names the REAL app name from the spec",
              '"My Notes"' in plan.says, plan.says)
        check("... and what will be built: native screens and how many",
              "native screens" in plan.says and "3 screens" in plan.says, plan.says)
        check("... and says it is not a web page", "not a web page" in plan.says, plan.says)
        check("the command is still gradlew.bat assembleDebug, exactly",
              plan.argv == [str(tdir / "gradlew.bat"), "assembleDebug"], plan.argv)
        check("... run in the task's copy", plan.cwd == tdir)
        check("... and the card carries the kind and screen count for the record",
              plan.detail()["app_kind"] == A.NATIVE and plan.detail()["screens"] == 3,
              plan.detail())
        check("the card still warns about the first build's download and the second card",
              "FIRST build" in plan.says and "second card" in plan.says)
        check("the install is not part of this card",
              "install -r" not in plan.says and "adb" not in plan.says)


def t_a_broken_spec_is_refused_before_the_card():
    A._reset_for_tests()
    name, task, tdir = built()
    (tdir / A.SPEC_ASSET).write_text("{ this is not json", encoding="utf-8")
    gate = Gate()
    store = types.SimpleNamespace(app_of=lambda _pid: {"app": name, "name": "Native"})
    with FakeToolchain(_TMP / "tc-broken"):
        code, body = A.handle_post(
            f"/api/projects/p1/app/tasks/{task}/android/build", {}, here=True,
            store=store, gate=gate, tier_of=lambda a: _TIER.get(a, "ask"),
            spawn=now_spawn)
        check("a build over a broken spec is refused, in plain words",
              code == 400 and "not valid JSON" in body["error"], (code, body))
        check("... and NO card was raised", gate.calls == [], gate.calls)
        plan = A.plan_build(name, task)
        check("... the plan is refused and its command is empty, so nothing could run",
              plan.refused != "" and plan.argv == [], (plan.refused, plan.argv))
        status = A.status(name, task)
        check("... and the status still answers instead of raising",
              status["ok"] is True and status["kind"] == A.NATIVE, status.get("kind"))


def t_the_install_card_names_the_app():
    name, task, tdir = built()
    apk = tdir / A.APK_REL
    apk.parent.mkdir(parents=True, exist_ok=True)
    apk.write_bytes(b"PK\x03\x04" + b"n" * 32)
    with FakeToolchain(_TMP / "tc-install"):
        plan = A.plan_install(name, task)
        check("an install plan exists once the APK is there", plan.refused == "", plan.refused)
        check("the install card names the real app", '"My Notes"' in plan.says, plan.says)
        check("... and the APK's own size", "KB" in plan.says)
        check("the install command is still adb install -r <apk>",
              plan.argv[1:3] == ["install", "-r"] and plan.argv[3] == str(apk), plan.argv)


# --------------------------------------------------------------------------
#   The routes, and the task's own files choosing the kind
# --------------------------------------------------------------------------


def t_the_template_route_writes_a_native_project():
    A._reset_for_tests()
    name, task = fresh()
    put_spec(name, task)
    store = types.SimpleNamespace(app_of=lambda _pid: {"app": name, "name": "Native"})
    gate = Gate()
    code, body = A.handle_post(
        f"/api/projects/p1/app/tasks/{task}/android/template", {}, here=True, store=store,
        gate=gate, tier_of=lambda a: _TIER.get(a, "ask"), spawn=now_spawn)
    check("the template route writes the native project", code == 200 and body["ok"] is True,
          (code, body))
    check("... and answers with the status saying native and three screens",
          body["status"]["kind"] == A.NATIVE and body["status"]["screens"] == 3,
          body.get("status"))
    check("... no card was needed to WRITE the project", gate.calls == [])
    code, body = A.handle_post(
        f"/api/projects/p1/app/tasks/{task}/android/template", {}, here=True, store=store,
        gate=gate, tier_of=lambda a: _TIER.get(a, "ask"), spawn=now_spawn)
    check("a second template write is refused, never a silent overwrite",
          code == 400 and "already" in body["error"], (code, body))

    name2, task2 = fresh()
    put_spec(name2, task2)
    store2 = types.SimpleNamespace(app_of=lambda _pid: {"app": name2, "name": "Native"})
    code, body = A.handle_post(
        f"/api/projects/p1/app/tasks/{task2}/android/template",
        {"assets": {"index.html": "<h1>x</h1>"}}, here=True, store=store2, gate=Gate(),
        tier_of=lambda a: _TIER.get(a, "ask"), spawn=now_spawn)
    check("a page passed beside a native spec is refused, not overwritten",
          code == 400 and "no web page" in body["error"], (code, body))
    code, body = A.handle_post(
        f"/api/projects/p1/app/tasks/{task2}/android/template", {"title": "Other"},
        here=True, store=store2, gate=Gate(), tier_of=lambda a: _TIER.get(a, "ask"),
        spawn=now_spawn)
    check("a title passed beside a native spec is refused, so there is one source",
          code == 400 and "app.json" in body["error"], (code, body))
    check("... and the task still has no project",
          not (W.task_dir(name2, task2) / "settings.gradle.kts").exists())


# --------------------------------------------------------------------------
#   The WebView kind is unchanged
# --------------------------------------------------------------------------


def t_the_webview_kind_is_unchanged():
    name, task = fresh()
    tdir = W.task_dir(name, task)
    plan = A.plan_template(name, task, title="My Page", background="#102030",
                           accent="#ffcc00")
    check("a task WITHOUT app.json is still the WebView kind",
          plan.kind == A.WEBVIEW and plan.refused == "", (plan.kind, plan.refused))
    check("... with the title and colours it was given",
          plan.title == "My Page" and plan.background == "#102030"
          and plan.accent == "#ffcc00")
    done = A.write_template(plan)
    check("it writes the same 15 paths as before",
          done["files"] == 15 and done["files"] == len(A.template_paths(name)),
          (done["files"], len(A.template_paths(name))))
    for rel in A.template_paths(name):
        check(f"written: {rel}", (tdir / rel).is_file())
    check("the WebView app has NO app.json in its assets",
          not (tdir / A.SPEC_ASSET).exists())
    check("... and no app.json at the root (the model wrote no spec)",
          not (tdir / A.SPEC_FILE).exists())
    activity = _read(tdir / "app/src/main/java/com/jarvis/made" / name / "MainActivity.kt")
    check("its activity is still the WebView one, byte for byte",
          activity == A._fill(A._MAIN_ACTIVITY, package="com.jarvis.made." + name))
    check("... loading the owner's page from assets",
          'loadUrl("file:///android_asset/index.html")' in activity)
    page = _read(tdir / A.ASSET_DIR / "index.html")
    check("... with the default page written when none was given",
          "My Page" in page and "app.css" in page)
    css = _read(tdir / A.ASSET_DIR / "app.css")
    check("... using the two colours it was given",
          "#102030" in css and "#ffcc00" in css, css[:80])
    name3, task3 = fresh()
    plan = A.plan_template(name3, task3, assets={"settings.gradle.kts": "x"})
    check("a fourth web file is still refused with the old words",
          "not one of this project's files" in plan.refused, plan.refused)
    plan = A.plan_template(name, "0" * 12)
    check("a task that is not there is still refused", "gone" in plan.refused, plan.refused)
    with FakeToolchain(_TMP / "tc-web"):
        name2, task2 = fresh()
        A.write_template(A.plan_template(name2, task2))
        plan = A.plan_build(name2, task2)
        check("a WebView build card still names the folder, not a spec",
              f'Build the Android app "{name2}"' in plan.says
              and "native screens" not in plan.says, plan.says)
        check("... and reports the webview kind", plan.detail()["app_kind"] == A.WEBVIEW,
              plan.detail())


def t_the_same_task_files_choose_the_kind():
    """The choice is the task's own files, so there is no flag to drift."""
    name, task = fresh()
    tdir = W.task_dir(name, task)
    check("before a spec: the task is WebView",
          A.task_kind(tdir) == A.WEBVIEW and A.project_kind(tdir) == "")
    put_spec(name, task)
    check("after the model writes app.json: the task is native",
          A.task_kind(tdir) == A.NATIVE)
    A.write_template(A.plan_template(name, task))
    check("a written native project says native", A.project_kind(tdir) == A.NATIVE)
    check("... and its status agrees", A.status(name, task)["kind"] == A.NATIVE)


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
