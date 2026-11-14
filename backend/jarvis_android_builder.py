"""jarvis_android_builder.py - from the owner's words to an app on their phone.

WHAT IT IS FOR
The owner asked (2026-10-30): "can jarvis build android apps? that i can
sideload into my phone? if not add them". `docs/APP-BUILDER-DESIGN.md` is the
plan; milestones C ("run a command") and G ("put it on the phone") had never
been built, and F ("native Android projects") had not either. This module is
the first real slice of all three, and it is deliberately the NARROWEST one
that ends with an app on the phone:

  1. TEMPLATE. A FIXED, minimal Android project is written into one task's
     copy (`jarvis_app_workspace`): the Gradle files, the manifest, one
     activity, and either the owner's own web page or the model's own screens.
     Jarvis - which means the local model - supplies ONLY the page
     (`index.html` / `app.js` / `app.css`, a name and two colours) or, for the
     second kind, ONE JSON spec (`app.json`). It never supplies a Gradle file,
     a Kotlin file or a manifest. Those are strings in this module, and the
     only thing that varies inside them is a VALIDATED name, package, colour
     or title. So the model cannot add a permission, a dependency, a network
     address or a receiver: the worst it can do is write a bad web page, or a
     spec the checks below refuse.
  2. BUILD. `gradlew.bat assembleDebug`, exactly, inside the task's copy,
     behind its OWN approval card (`app_build_android`), with the
     allowlisted environment every program Jarvis starts gets
     (`jarvis_child_env`: never a token, key or password), a time limit and
     an output cap.
  3. INSTALL. `adb install -r <the .apk this build made>`, exactly, behind
     its own card (`app_install_android`), with adb called by FULL PATH and
     with no other adb subcommand available anywhere in this module. There is
     no `adb shell`, no `uninstall`, no `-s <serial>` and no free-form
     argument: the only thing that varies is one path, and that path must be
     a real `.apk` inside the task's own copy.

WHY A FIXED TEMPLATE RATHER THAN THE MODEL WRITING AN APP
A small local model writing Kotlin, a manifest and a Gradle build that has
never been compiled is a machine for producing unbuildable projects, and
every failed build costs the owner minutes of fan noise. The template is the
part that must be right, so it is written once, here, by hand, and the model
gets the part it is actually good at: words and pixels. `docs/ANDROID-APP-
BUILDER-2026-10-30.md` (scratch, gitignored) records the two routes that were
compared and why this one was chosen.

THE SECOND KIND: NATIVE SCREENS (2026-11-14)
The owner asked for a real app with its own screens, not one page inside a
WebView. So a task may carry `app.json` - one JSON object the model writes,
describing at most 8 screens of three kinds (text, list, form), their buttons,
a start screen and two colours. A second fixed Kotlin activity in this module
reads that file from `assets/app.json` at run time and draws it with ordinary
Android views (ScrollView, LinearLayout, TextView, EditText, Button): no
Compose, no WebView, no dependency. The model writes DATA, never code - and
the whole spec is validated HERE, before a byte of the project is written and
before any card is raised, so it cannot smuggle in a permission, a path, an id
outside the closed pattern, a button that opens a screen that does not exist,
or an unknown key. A form saves its values to SharedPreferences on the phone
and nothing else; a button opens another screen or shows one short line.
THIS TASK'S OWN FILES CHOOSE THE KIND: a task that carries `app.json` is a
native-screens task, and a task without one is the WebView app it has always
been. There is no separate flag that could drift out of step with the files.

WHY THE GENERATED APP HAS NO PERMISSIONS AT ALL
The manifest declares no `<uses-permission>` - not even INTERNET - and the
WebView is built with file access off and every navigation refused. The
native-screens activity has no WebView at all and draws only the views its
validated spec names. So either app the owner sideloads cannot reach the
internet, cannot read their files and cannot call Jarvis's own routes: rule 1
and rule 2 hold by construction rather than by promise. An app that needs to
talk to something is a separate decision with its own card, and it is not this
slice.

WHAT RUNS WHERE, AND WHAT EACH CARD SAYS
  * Writing the template: NO card. It writes files into a task's own copy -
    the same rule as every other file Jarvis writes (APP-BUILDER-DESIGN.md,
    "Write files in a task's copy: no card"). Nothing is executed.
  * Building: ONE card, `app_build_android`, tier "ask", RISKY (it runs
    Gradle, which runs other people's build code with the owner's Windows
    permissions - ARCHITECTURE.md section 11 says a worktree is not a
    sandbox). The card carries the exact command, the exact folder, the
    exact toolchain found on this PC, and the plain fact that a FIRST build
    downloads the Gradle distribution and the Android Gradle plugin from the
    internet. Nothing of the owner's is sent: a download is a GET with no
    body.
  * Installing: ONE card, `app_install_android`, tier "ask", RISKY (it
    changes what is on the phone, and there is no uninstall button here).
    The card carries the exact `adb` command, the exact APK file and its
    size, and says it is a sideload - never a store.

WHAT IS IN THE CHILD PROCESS'S ENVIRONMENT
`jarvis_child_env.inherited()` - the same allowlist every program Jarvis
starts gets - plus the three PATHS the Android toolchain needs and nothing
else: `ANDROID_HOME`, `ANDROID_SDK_ROOT` (both pointing at the SDK this
module found) and `JAVA_HOME`. `GRADLE_USER_HOME` is inherited only if the
owner set it. No token, no key, no password: `inherited()` drops anything
whose name looks like a secret, and a test in `backend/test_android_builder.py`
proves a token in the parent's environment does not reach either command.

WHAT IS KEPT ON DISK
Only inside the task's copy: the project, and the build's own log at
`build/jarvis-build.log` (gitignored, so it never reaches the merge card).
The card state is in memory, like `jarvis_apps`': a backend restart drops a
waiting card and the task simply stays, so it can be built again.

WHAT THIS MODULE DOES NOT DO
No `npm`, no Capacitor, no release signing, no Play Store (rule 5), no
`adb shell`, no device management, no arbitrary command, and no model call.
For the native-screens kind: no Compose, no WebView, no dependency, no
permission, no internet call, no file read outside the app's own `assets/`,
and no code of any kind from the model - it writes one JSON spec and the
activity that draws it is a string in this module. The Gradle task name and
both commands are module constants.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

import jarvis_app_workspace as W
import jarvis_projects as P

#: The kind of app this module builds (`jarvis_app_workspace.KINDS`).
KIND = "android"

#: The two approval cards' actions. Both are tier "ask" in
#: `backend/rebuilt/jarvis-framework.toml` and both are RISKY in
#: `jarvis_gate._RISK` (reversible "no"): Windows Hello on the PC, the screen
#: lock on the phone. Both are in `jarvis_gate._NO_RULE_FROM_DENIAL`, because
#: they always ask and a "no" must not become a standing rule.
BUILD_ACTION = "app_build_android"
INSTALL_ACTION = "app_install_android"

#: The two kinds of Android app this module builds. The kind is chosen by the
#: TASK, from the task's own files and nothing else: a task that carries
#: `app.json` (the model's spec) is a native-screens task, and a task without
#: one is the WebView app. There is no separate flag that could drift.
WEBVIEW = "webview"
NATIVE = "native"

#: The ONLY web files Jarvis may write into the WebView project. A closed
#: list: the model's answer is looked up in it, never used as a path.
ASSETS = ("index.html", "app.js", "app.css")
ASSET_DIR = "app/src/main/assets"

#: The ONE file the model writes for a native-screens app, at the root of the
#: task's copy. The validated copy is what ships, inside `assets/`.
SPEC_FILE = "app.json"
SPEC_ASSET = f"{ASSET_DIR}/{SPEC_FILE}"

#: The hard limits of a spec, refused in plain words before anything is
#: written and before any card. They bound what the phone will draw and what
#: the owner can be shown: a 1,000-screen app, or a 40 KB title, is not a
#: small app and could not be read on one card. A spec the model can write is
#: at most 512 KB (the workspace's own file limit), so nothing legal is cut off.
MAX_SPEC_BYTES = 512 * 1024
MAX_SCREENS = 8
MAX_ITEMS = 40
MAX_FIELDS = 6
MAX_BUTTONS = 4
MAX_TEXT = 400
MAX_LABEL = 40

#: The only OS this feature claims: the Android SDK, the phone's cable and the
#: owner's own toolchain are on a Windows PC. Read at CALL time (never baked
#: into a constant), so a test can prove the Windows path on a Linux runner.
WINDOWS = os.name == "nt"

#: The one Gradle task this module will run, and the only file it will
#: install. Both are constants, not parameters.
GRADLE_TASK = "assembleDebug"
APK_REL = "app/build/outputs/apk/debug/app-debug.apk"
BUILD_LOG_REL = "build/jarvis-build.log"

#: The fixed toolchain. These are the versions `jarvis-client` already builds
#: with on this PC (its own wrapper properties and root build file), so the
#: owner is not asked to trust a second set of numbers. Nothing here is a
#: guess: `backend/test_android_builder.py` reads `jarvis-client`'s files and
#: checks the template's constants against them.
GRADLE_VERSION = "9.6.0"
GRADLE_DIST_SHA256 = "bbaeb2fef8710818cf0e261201dab964c572f92b942812df0c3620d62a529a01"
AGP_VERSION = "9.4.0"
COMPILE_SDK = 36
MIN_SDK = 33
TARGET_SDK = 36

#: A single asset is small on purpose: a page bigger than this is not a small
#: app any more, and the merge card could not show it.
MAX_ASSET_BYTES = 96 * 1024
#: A build downloads Gradle (~130 MB) and the plugin on its FIRST run, so the
#: limit has to be generous. It is a limit, not a promise.
BUILD_SECONDS = 1500.0
INSTALL_SECONDS = 180.0
#: What the card and the API show of the build's output: the END of it, which
#: is where a failure says why.
MAX_LOG_CHARS = 12_000

#: How a card ended, word for word.
OUTCOME_WORDS = {
    "built": "Built. The APK is ready to put on your phone.",
    "installed": "Installed on your phone.",
    "denied": "Not done - you said no.",
    "timed_out": "Not done - the card timed out.",
    "refused": "Not done.",
    "withdrawn": "Not done - the task was thrown away before you answered.",
    "failed": "Not done - something went wrong. Nothing was changed.",
}

CARD_WAITING = "A card for this app is already waiting - answer it first."
NO_TASK = "No such task."
PC_ONLY = "Building and installing happen on the PC that has the Android SDK and " \
          "the phone on its cable."
NOT_ANDROID = "This project is not an Android app."
NOT_TEMPLATE = "This task has no Android project yet."
BUILD_FIRST = "There is no APK to install yet - build the app first."

_PKG_TAIL = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
#: A title goes into an Android string resource, which treats `'` and `"` as
#: delimiters - an unescaped apostrophe is a BUILD ERROR. So the allowed set
#: is deliberately narrow, and quotes are not in it.
_TITLE_OK = re.compile(r"^[A-Za-z0-9 .,!?():+-]{1,40}$")

_S_LOCK = threading.RLock()
_S_STATE: dict = {"pending": {}, "withdrawn": set(), "silent": set(), "last": {}}
#: Held while a card's yes runs its command, so two commands never overlap.
_S_ONE = threading.RLock()


class BuildRefused(Exception):
    """A plain-words reason something was refused or failed."""


# --------------------------------------------------------------------------
#   The fixed project: every text file the template writes
# --------------------------------------------------------------------------

#: How a template's own values are filled in. A plain token replace, NOT
#: `str.format`: these are Gradle, Kotlin, XML and the owner's own CSS and
#: JavaScript, and every one of those is full of braces. A stray `{` that
#: Python read as a field is a build error on the owner's PC and nothing here
#: would have caught it (2026-10-30).
_TITLE, _PACKAGE, _BG, _ACCENT, _AGP = "__JARVIS_TITLE__", "__JARVIS_PACKAGE__", \
    "__JARVIS_BACKGROUND__", "__JARVIS_ACCENT__", "__JARVIS_AGP__"
_CSDK, _MSDK, _TSDK = "__JARVIS_COMPILE_SDK__", "__JARVIS_MIN_SDK__", "__JARVIS_TARGET_SDK__"
_TOKENS = (_TITLE, _PACKAGE, _BG, _ACCENT, _AGP, _CSDK, _MSDK, _TSDK)


def _fill(text: str, **values) -> str:
    """One template with its `__JARVIS_*__` tokens replaced. A token with no
    value is refused rather than shipped, so a template can never reach the
    owner's PC with a placeholder still in it."""
    for key, value in values.items():
        text = text.replace({"title": _TITLE, "package": _PACKAGE, "background": _BG,
                             "accent": _ACCENT, "agp": _AGP, "compile_sdk": _CSDK,
                             "min_sdk": _MSDK, "target_sdk": _TSDK}[key], str(value))
    leftover = [t for t in _TOKENS if t in text]
    if leftover:
        raise BuildRefused("a template value was not filled in: " + ", ".join(leftover))
    return text


#: The project's own files. Written with LF endings, like every text file this
#: repository produces, so the bytes are the same on Windows and on CI.
_SETTINGS_GRADLE = '''\
// Written by Jarvis. Do not edit: the app's own files are the web page in
// app/src/main/assets/, and the model never writes this file
// (docs/APP-BUILDER-DESIGN.md, milestone F).
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "__JARVIS_TITLE__"
include(":app")
'''

_BUILD_GRADLE = '''\
// The Android Gradle plugin (the tool that builds an Android app) is pinned to
// the version jarvis-client already builds with on this PC - one toolchain,
// one set of downloads.
plugins {
    id("com.android.application") version "__JARVIS_AGP__" apply false
}
'''

_GRADLE_PROPERTIES = '''\
# A fixed, small build: no configuration cache (a first build downloads its
# plugins, and the cache would store a path that moves), no AndroidX anywhere
# in the app - it has no dependencies at all.
#
# Measured 2026-10-30: this file used to set `android.useAndroidX=false`, and
# Android Gradle plugin 9.4.0 answered "The option setting
# 'android.useAndroidX=false' is deprecated... It will be removed in version
# 10.0" on every build. The app uses no AndroidX library, so the setting bought
# nothing and is gone rather than carried into a build that will refuse it.
org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
android.nonTransitiveRClass=true
kotlin.code.style=official
'''

_WRAPPER_PROPERTIES = f'''\
# The Gradle wrapper: the build downloads THIS version of Gradle and checks
# it against the SHA-256 below, so a tampered download is refused rather
# than run. The number and the sum are jarvis-client's own.
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-{GRADLE_VERSION}-bin.zip
distributionSha256Sum={GRADLE_DIST_SHA256}
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
'''

_APP_BUILD_GRADLE = '''\
// One app, no dependencies, no permissions: the whole app is the WebView and
// the owner's page in ../assets. Adding a dependency here is a code change to
// Jarvis, not something a model may write.
plugins {
    id("com.android.application")
}

android {
    namespace = "__JARVIS_PACKAGE__"
    compileSdk = __JARVIS_COMPILE_SDK__

    defaultConfig {
        applicationId = "__JARVIS_PACKAGE__"
        minSdk = __JARVIS_MIN_SDK__
        targetSdk = __JARVIS_TARGET_SDK__
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        // Debug only, and never shrunk: the owner sideloads this build and
        // nothing else (rule 5). A release build would need a real signing
        // key, which is a decision this slice does not take.
        getByName("debug") {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
'''


_MANIFEST = '''\
<?xml version="1.0" encoding="utf-8"?>
<!--
  Jarvis made this. There is NO permission line on purpose: the app cannot
  reach the internet, cannot read your files and cannot call Jarvis's own
  routes. The only thing it can do is draw the page in assets/.
-->
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <application
        android:allowBackup="false"
        android:label="@string/app_name"
        android:supportsRtl="true"
        android:theme="@style/JarvisAppTheme"
        android:usesCleartextTraffic="false">

        <activity
            android:name=".MainActivity"
            android:configChanges="orientation|screenSize|keyboardHidden|screenLayout"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
'''

_MAIN_ACTIVITY = '''\
package __JARVIS_PACKAGE__

import android.app.Activity
import android.os.Bundle
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient

/**
 * One screen: the page in `assets/`, and nothing else.
 *
 * The three settings below are the whole of the app's safety:
 *   * [WebSettings.setAllowFileAccess] is off, so the page cannot read the
 *     phone's files through `file://`;
 *   * [WebSettings.setAllowContentAccess] is off, so it cannot read the
 *     phone's shared content either;
 *   * `StayOnThisPage` refuses EVERY navigation, so a link - even one in the
 *     owner's own HTML - cannot take the WebView anywhere. The manifest has
 *     no internet permission, so nothing outside the phone was reachable
 *     anyway; this makes the inside honest too.
 *
 * Written by Jarvis. The owner's own words and pixels are in
 * `src/main/assets/index.html`, `app.css` and `app.js`.
 */
class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val page = WebView(this)
        val settings: WebSettings = page.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.allowFileAccess = false
        settings.allowContentAccess = false
        settings.cacheMode = WebSettings.LOAD_NO_CACHE
        page.webViewClient = StayOnThisPage()
        page.loadUrl("file:///android_asset/index.html")
        setContentView(page)
    }

    /** Every navigation is refused: the app has exactly one page. */
    private class StayOnThisPage : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = true
    }
}
'''


#: The native-screens app: ONE fixed activity that reads `assets/app.json` and
#: builds the screens with ordinary Android views. No Compose, no WebView, no
#: library, no permission. The model's spec is data; every view below is a
#: widget from the Android framework, and the only strings that vary are the
#: package (validated) - the spec itself is read at run time.
_MAIN_ACTIVITY_SCREENS = '''\
package __JARVIS_PACKAGE__

import android.app.Activity
import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.util.TypedValue
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject

/**
 * The app's own screens, built at run time from `assets/app.json`.
 *
 * This is the whole app: one fixed activity and no code from the model. The
 * file it reads is DATA - titles, paragraphs, list rows, form fields, buttons
 * and two colours - and every view below is an ordinary Android widget. There
 * is no WebView, so there is no page, no script and no `file://` access; there
 * is no Compose and no dependency, so the build is the same fixed one the
 * WebView app uses, and the manifest declares no permission at all.
 *
 * A form's values are kept with [Context.getSharedPreferences] on the phone
 * and nowhere else; its button shows a short confirmation. A button either
 * opens another screen or shows one short line in a [Toast]. The spec is
 * written from a model's answer, so it can only say what the fixed checks in
 * `jarvis_android_builder.py` allow - the activity trusts its own data
 * because those checks ran before the build.
 */
class MainActivity : Activity() {

    private val screens = LinkedHashMap<String, JSONObject>()
    private val history = ArrayList<String>()
    private lateinit var page: LinearLayout
    private var background: Int = Color.parseColor("#101828")
    private var accent: Int = Color.parseColor("#7cc4ff")
    private var ink: Int = Color.parseColor("#f2f4f8")
    private var faded: Int = Color.parseColor("#b9c2d0")
    private var current: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val spec = readSpec()
        if (spec == null) {
            val sorry = TextView(this)
            sorry.text = "This app's screens are missing or could not be read."
            sorry.setTextColor(Color.WHITE)
            sorry.setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
            sorry.setPadding(dp(24), dp(32), dp(24), dp(24))
            setContentView(sorry)
            return
        }
        background = colour(spec.optString("bg"), Color.parseColor("#101828"))
        accent = colour(spec.optString("accent"), Color.parseColor("#7cc4ff"))
        ink = readable(background)
        faded = withAlpha(ink, 168)
        val listed = spec.optJSONArray("screens") ?: JSONArray()
        for (i in 0 until listed.length()) {
            val screen = listed.optJSONObject(i) ?: continue
            val id = screen.optString("id")
            if (id.isNotEmpty()) {
                screens[id] = screen
            }
        }
        page = LinearLayout(this)
        page.orientation = LinearLayout.VERTICAL
        page.setPadding(dp(20), dp(28), dp(20), dp(36))
        page.setBackgroundColor(background)
        val scroll = ScrollView(this)
        scroll.isFillViewport = true
        scroll.setBackgroundColor(background)
        scroll.addView(page, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        setContentView(scroll)
        show(spec.optString("start"))
    }

    /**
     * Android's own Back goes to the screen the owner came from. It is
     * deprecated on Android 13, and this app carries no AndroidX library to
     * use the replacement - so the deprecation is accepted rather than adding
     * a dependency the whole design exists to avoid.
     */
    @Suppress("DEPRECATION", "OVERRIDE_DEPRECATION")
    override fun onBackPressed() {
        if (history.isEmpty()) {
            super.onBackPressed()
        } else {
            show(history.removeAt(history.size - 1))
        }
    }

    /** The spec, or null when the asset is missing or is not JSON. */
    private fun readSpec(): JSONObject? {
        return try {
            JSONObject(assets.open("app.json").bufferedReader(Charsets.UTF_8).use { it.readText() })
        } catch (exc: Exception) {
            null
        }
    }

    /** Draws one screen. The spec was validated before the build, so a screen
     *  that is not here means the asset was changed by hand: say so, quietly. */
    private fun show(id: String) {
        page.removeAllViews()
        val screen = screens[id]
        if (screen == null) {
            page.addView(label("That screen is missing.", 17f, ink, false, 0))
            return
        }
        current = id
        page.addView(label(screen.optString("title"), 27f, ink, true, 0))
        when (screen.optString("kind")) {
            "text" -> paragraphs(screen.optJSONArray("body"))
            "list" -> items(screen.optJSONArray("items"))
            "form" -> form(screen)
        }
        buttons(screen)
    }

    private fun paragraphs(body: JSONArray?) {
        if (body == null) {
            return
        }
        for (i in 0 until body.length()) {
            page.addView(label(body.optString(i), 16f, faded, false, 18))
        }
    }

    private fun items(items: JSONArray?) {
        if (items == null) {
            return
        }
        for (i in 0 until items.length()) {
            val item = items.optJSONObject(i) ?: continue
            val row = LinearLayout(this)
            row.orientation = LinearLayout.VERTICAL
            row.setPadding(0, dp(12), 0, dp(12))
            row.addView(label(item.optString("title"), 17f, ink, true, 0))
            row.addView(label(item.optString("detail"), 14f, faded, false, 4))
            page.addView(row)
        }
    }

    private fun form(screen: JSONObject) {
        val fields = screen.optJSONArray("fields") ?: JSONArray()
        val saved = getSharedPreferences("jarvis_native_screens", Context.MODE_PRIVATE)
        val inputs = ArrayList<EditText>()
        for (i in 0 until fields.length()) {
            val field = fields.optJSONObject(i) ?: continue
            val key = field.optString("key")
            page.addView(label(field.optString("label"), 14f, faded, false, 20))
            val input = EditText(this)
            input.tag = key
            input.setText(saved.getString(key, ""))
            input.setTextColor(ink)
            input.setHintTextColor(faded)
            input.inputType = InputType.TYPE_CLASS_TEXT
            input.backgroundTintList = ColorStateList.valueOf(accent)
            page.addView(input)
            inputs.add(input)
        }
        val save = Button(this)
        save.text = screen.optString("save_label")
        save.setTextColor(readable(accent))
        save.backgroundTintList = ColorStateList.valueOf(accent)
        save.setOnClickListener {
            val edit = saved.edit()
            for (input in inputs) {
                val key = input.tag as? String ?: continue
                edit.putString(key, input.text.toString())
            }
            edit.apply()
            Toast.makeText(this, "Saved on this phone.", Toast.LENGTH_SHORT).show()
        }
        val params = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        params.topMargin = dp(22)
        page.addView(save, params)
    }

    private fun buttons(screen: JSONObject) {
        val listed = screen.optJSONArray("buttons") ?: return
        for (i in 0 until listed.length()) {
            val button = listed.optJSONObject(i) ?: continue
            val action = button.optJSONObject("action") ?: continue
            val view = Button(this)
            view.text = button.optString("label")
            view.setTextColor(readable(accent))
            view.backgroundTintList = ColorStateList.valueOf(accent)
            view.setOnClickListener {
                if (action.optString("do") == "open") {
                    val target = action.optString("screen")
                    if (screens.containsKey(target)) {
                        history.add(current)
                        show(target)
                    }
                } else {
                    Toast.makeText(this, action.optString("text"), Toast.LENGTH_SHORT).show()
                }
            }
            val params = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            params.topMargin = dp(12)
            page.addView(view, params)
        }
    }

    private fun label(text: String, size: Float, colour: Int, bold: Boolean,
                      top: Int): TextView {
        val view = TextView(this)
        view.text = text
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, size)
        view.setTextColor(colour)
        if (bold) {
            view.setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        }
        view.setLineSpacing(0f, 1.15f)
        if (top > 0) {
            view.setPadding(0, dp(top), 0, 0)
        }
        return view
    }

    private fun colour(value: String, fallback: Int): Int {
        return try {
            Color.parseColor(value)
        } catch (exc: Exception) {
            fallback
        }
    }

    /** A text colour that reads on the given background, light or dark. */
    private fun readable(on: Int): Int {
        val level = 0.299 * Color.red(on) + 0.587 * Color.green(on) + 0.114 * Color.blue(on)
        return if (level > 150.0) Color.parseColor("#101828") else Color.parseColor("#f2f4f8")
    }

    private fun withAlpha(colour: Int, alpha: Int): Int {
        return Color.argb(alpha, Color.red(colour), Color.green(colour), Color.blue(colour))
    }

    private fun dp(value: Int): Int {
        return (value * resources.displayMetrics.density + 0.5f).toInt()
    }
}
'''

_THEMES = '''\
<?xml version="1.0" encoding="utf-8"?>
<!-- The window's colours come from colors.xml, which is one of the two
     values Jarvis is allowed to be given. No library theme: an app with no
     dependencies has no AppCompat to inherit from. -->
<resources>
    <style name="JarvisAppTheme" parent="android:Theme.Material.NoActionBar">
        <item name="android:windowBackground">@color/jarvis_background</item>
        <item name="android:colorAccent">@color/jarvis_accent</item>
        <item name="android:statusBarColor">@color/jarvis_background</item>
        <item name="android:navigationBarColor">@color/jarvis_background</item>
        <item name="android:windowLightStatusBar">false</item>
    </style>
</resources>
'''

#: The page Jarvis writes when the owner (or the model) supplies nothing. It
#: is a working app on its own, which is what makes the first build reachable
#: without a single model call.
_DEFAULT_INDEX = '''\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>__JARVIS_TITLE__</title>
<link rel="stylesheet" href="app.css">
</head>
<body>
<main>
  <h1>__JARVIS_TITLE__</h1>
  <p id="says">Made by Jarvis, on this PC.</p>
  <button id="tap" type="button">Say hello</button>
</main>
<script src="app.js"></script>
</body>
</html>
'''

_DEFAULT_CSS = '''\
:root { color-scheme: dark; }
html, body { margin: 0; height: 100%; }
body {
  background: __JARVIS_BACKGROUND__;
  color: #f2f4f8;
  font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  display: grid;
  place-items: center;
  padding: 24px;
  box-sizing: border-box;
}
main { text-align: center; max-width: 34rem; }
h1 { font-size: 1.9rem; margin: 0 0 .5rem; letter-spacing: -.02em; }
p { color: #b9c2d0; line-height: 1.5; }
button {
  margin-top: 1.2rem;
  padding: .8rem 1.4rem;
  border: 0;
  border-radius: 999px;
  background: __JARVIS_ACCENT__;
  color: #08101c;
  font: inherit;
  font-weight: 650;
}
'''

_DEFAULT_JS = '''\
// The page's own behaviour. Nothing here can reach the internet: the app has
// no internet permission at all.
(function () {
  var says = document.getElementById("says");
  var tap = document.getElementById("tap");
  var n = 0;
  if (tap) {
    tap.addEventListener("click", function () {
      n += 1;
      if (says) { says.textContent = "Hello from __JARVIS_TITLE__. That was tap " + n + "."; }
    });
  }
})();
'''



def package_name(name: str) -> str:
    """The Java package / application id for an app folder name.

    Lower-case letters, digits and underscores only (an app folder name also
    allows dashes, which are not legal in a package), never starting with a
    digit, prefixed so two Jarvis-made apps cannot collide with a real
    vendor's id."""
    W.check_name(name)
    tail = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")[:39]
    if not tail or not tail[0].isalpha():
        tail = "app_" + tail
    if not _PKG_TAIL.match(tail):
        raise BuildRefused(f"the app's name {name!r} cannot become an Android package name")
    return "com.jarvis.made." + tail


def check_title(title: str) -> str:
    """The app's name as the phone will show it. Deliberately narrow: this
    string goes into an Android string resource, where a stray apostrophe or
    `&` is a build error or a broken label."""
    text = " ".join(str(title or "").split())
    if not text or not _TITLE_OK.match(text):
        raise BuildRefused("an app's name may use letters, digits, spaces and . , ! ? ( ) : + - "
                           "(up to 40), and no quotes")
    return text


def check_colour(value: str, what: str) -> str:
    if not isinstance(value, str) or not _COLOUR.match(value.strip()):
        raise BuildRefused(f"{what} must be a colour like #101828")
    return value.strip().lower()


def _xml(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# --------------------------------------------------------------------------
#   The native-screens spec: the model's data, checked before anything
# --------------------------------------------------------------------------
#
# A spec is ONE JSON object, and every part of it is checked here: unknown keys
# are refused rather than ignored, every string has a length and a shape,
# every `open` names a screen that exists, and the ids are a closed pattern.
# The returned dict is the ONLY thing written into the app, so the bytes the
# phone reads are exactly the bytes that were checked.

#: A screen id AND a form field's key (which becomes a SharedPreferences key).
#: Small letters, digits, '-' and '_', starting with a letter, 24 at most. The
#: narrowness is the point: an id is a key in the activity's own table and a
#: field key reaches Android's own storage, so neither may contain a space, a
#: path separator, a dot or anything a preference name treats specially.
_SPEC_ID = re.compile(r"^[a-z][a-z0-9_-]{0,23}$")

_SCREEN_KINDS = ("text", "list", "form")
_SPEC_KEYS = frozenset({"name", "package_tail", "bg", "accent", "screens", "start"})
#: The spec's own key names in the words the owner reads. A refusal says
#: "app.json is missing its package ending", never the snake_case field name.
_SPEC_KEY_WORDS = {
    "name": "name",
    "package_tail": "package ending",
    "bg": "background colour",
    "accent": "accent colour",
    "screens": "screens",
    "start": "starting screen",
}
_SCREEN_KEYS = {
    "text": frozenset({"id", "title", "kind", "body", "buttons"}),
    "list": frozenset({"id", "title", "kind", "items", "buttons"}),
    "form": frozenset({"id", "title", "kind", "fields", "save_label", "buttons"}),
}
_ITEM_KEYS = frozenset({"title", "detail"})
_FIELD_KEYS = frozenset({"key", "label"})
_BUTTON_KEYS = frozenset({"label", "action"})
_ACTION_KEYS = {"open": frozenset({"do", "screen"}), "show": frozenset({"do", "text"})}


def _spec_unknown(given: dict, allowed, where: str) -> None:
    """Refuse a key the fixed activity would silently ignore. The model is
    told which key, and the whole spec is refused rather than half-honoured."""
    extra = sorted(k for k in given if k not in allowed)
    if extra:
        raise BuildRefused(f"{where} has a key this kind does not use: {str(extra[0])[:40]!r}")


def _spec_string(value, where: str, limit: int) -> str:
    """One validated piece of text. Whitespace is tidied to single spaces, so
    a length limit is a limit on what the phone draws; control characters are
    refused because they can hide the end of a line from the owner."""
    if not isinstance(value, str):
        raise BuildRefused(f"{where} must be text")
    text = " ".join(value.split())
    if not text:
        raise BuildRefused(f"{where} is empty")
    if any(ord(ch) < 0x20 for ch in text):
        raise BuildRefused(f"{where} has a control character in it")
    if len(text) > limit:
        raise BuildRefused(f"{where} is {len(text)} characters; at most {limit} are allowed")
    return text


def _spec_id(value, where: str) -> str:
    if not isinstance(value, str) or not _SPEC_ID.match(value):
        raise BuildRefused(f"{where} must be small letters, digits, '-' and '_' (up to 24), "
                           f"starting with a letter: {str(value)[:40]!r}")
    return value


def _spec_name(value) -> str:
    """The app's own name. Narrow like `check_title`, and for the same reason:
    it becomes Android's label for the app in `strings.xml`."""
    text = " ".join(value.split()) if isinstance(value, str) else ""
    if not text or not _TITLE_OK.match(text):
        raise BuildRefused(
            f"the app's name {str(value)[:40]!r} may use letters, digits, spaces and "
            ". , ! ? ( ) : + - (up to 40), and no quotes - it becomes Android's label "
            "for the app")
    return text


def _spec_items(items, sid: str) -> list:
    if not isinstance(items, list):
        raise BuildRefused(f"screen {sid!r}: items must be a list")
    if len(items) > MAX_ITEMS:
        raise BuildRefused(f"screen {sid!r} has {len(items)} items; at most {MAX_ITEMS} are "
                           "allowed")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise BuildRefused(f"an item on screen {sid!r} must be an object")
        _spec_unknown(item, _ITEM_KEYS, f"an item on screen {sid!r}")
        out.append({
            "title": _spec_string(item.get("title"),
                                  f"an item's title on screen {sid!r}", MAX_LABEL),
            "detail": _spec_string(item.get("detail"),
                                   f"an item's detail on screen {sid!r}", MAX_TEXT),
        })
    return out


def _spec_form(screen: dict, sid: str) -> tuple:
    fields = screen.get("fields")
    if not isinstance(fields, list):
        raise BuildRefused(f"screen {sid!r}: fields must be a list")
    if len(fields) > MAX_FIELDS:
        raise BuildRefused(f"screen {sid!r} has {len(fields)} fields; at most {MAX_FIELDS} "
                           "are allowed")
    out, keys = [], set()
    for field in fields:
        if not isinstance(field, dict):
            raise BuildRefused(f"a field on screen {sid!r} must be an object")
        _spec_unknown(field, _FIELD_KEYS, f"a field on screen {sid!r}")
        key = _spec_id(field.get("key"), f"a field's key on screen {sid!r}")
        if key in keys:
            raise BuildRefused(f"screen {sid!r} has two fields with the key {key!r}")
        keys.add(key)
        out.append({"key": key,
                    "label": _spec_string(field.get("label"),
                                          f"a field's label on screen {sid!r}", MAX_LABEL)})
    save = _spec_string(screen.get("save_label"), f"the Save button's words on screen {sid!r}", MAX_LABEL)
    return out, save


def _spec_buttons(screen: dict, sid: str) -> tuple:
    buttons = screen.get("buttons", [])
    if not isinstance(buttons, list):
        raise BuildRefused(f"screen {sid!r}: buttons must be a list")
    if len(buttons) > MAX_BUTTONS:
        raise BuildRefused(f"screen {sid!r} has {len(buttons)} buttons; at most {MAX_BUTTONS} "
                           "are allowed")
    out, targets = [], []
    for button in buttons:
        if not isinstance(button, dict):
            raise BuildRefused(f"a button on screen {sid!r} must be an object")
        _spec_unknown(button, _BUTTON_KEYS, f"a button on screen {sid!r}")
        label = _spec_string(button.get("label"), f"a button's label on screen {sid!r}",
                             MAX_LABEL)
        action = button.get("action")
        if not isinstance(action, dict):
            raise BuildRefused(f"the button {label!r} on screen {sid!r} needs an action")
        do = action.get("do")
        if do not in _ACTION_KEYS:
            raise BuildRefused(f"a button on screen {sid!r} asks to {str(do)[:40]!r}; it may "
                               "only \"open\" a screen or \"show\" a line of text")
        _spec_unknown(action, _ACTION_KEYS[do], f"a button on screen {sid!r}")
        if do == "open":
            target = _spec_id(action.get("screen"), f"a button's open target on screen {sid!r}")
            out.append({"label": label, "action": {"do": "open", "screen": target}})
            targets.append((sid, target))
        else:
            out.append({"label": label,
                        "action": {"do": "show",
                                   "text": _spec_string(action.get("text"),
                                                        f"a button's text on screen {sid!r}",
                                                        MAX_TEXT)}})
    return out, targets


def validate_spec(raw) -> dict:
    """The model's `app.json` -> the validated spec, or a plain-words refusal.

    Every key is checked and every unknown one refused, never ignored: a model
    that writes `"permissions"` (or a key belonging to the other screen kind)
    is told so and nothing is built. The returned dict is the ONLY version that
    is written into the app, so the shipped bytes are the checked bytes."""
    if not isinstance(raw, dict):
        raise BuildRefused("app.json must be one JSON object holding the app's own keys - "
                           "a name, a package ending, two colours, its screens and the "
                           "screen it starts on")
    _spec_unknown(raw, _SPEC_KEYS, "app.json")
    for key in ("name", "package_tail", "bg", "accent", "screens", "start"):
        if key not in raw:
            raise BuildRefused(f"app.json is missing its {_SPEC_KEY_WORDS[key]}")
    name = _spec_name(raw.get("name"))
    tail = raw.get("package_tail")
    if not isinstance(tail, str) or not _PKG_TAIL.match(tail):
        raise BuildRefused("the package ending must be small letters, digits and _ (up to 40), "
                           f"starting with a letter: {str(tail)[:40]!r}")
    bg = check_colour(raw.get("bg"), "app.json's bg")
    accent = check_colour(raw.get("accent"), "app.json's accent")
    screens = raw.get("screens")
    if not isinstance(screens, list):
        raise BuildRefused("app.json's screens must be a list")
    if not screens:
        raise BuildRefused("an app needs at least one screen")
    if len(screens) > MAX_SCREENS:
        raise BuildRefused(f"this app has {len(screens)} screens; at most {MAX_SCREENS} are "
                           "allowed")
    out, ids, targets = [], [], []
    for index, screen in enumerate(screens):
        where = f"screen {index + 1}"
        if not isinstance(screen, dict):
            raise BuildRefused(f"{where} must be an object")
        sid = _spec_id(screen.get("id"), f"{where}'s id")
        if sid in ids:
            raise BuildRefused(f"two screens have the id {sid!r}")
        ids.append(sid)
        kind = screen.get("kind")
        if kind not in _SCREEN_KINDS:
            raise BuildRefused(f"screen {sid!r}'s kind must be \"text\", \"list\" or \"form\", "
                               f"not {str(kind)[:40]!r}")
        _spec_unknown(screen, _SCREEN_KEYS[kind], f"screen {sid!r}")
        row = {"id": sid,
               "title": _spec_string(screen.get("title"), f"screen {sid!r}'s title", MAX_LABEL),
               "kind": kind}
        if kind == "text":
            body = screen.get("body")
            if not isinstance(body, list):
                raise BuildRefused(f"screen {sid!r}: body must be a list of paragraphs")
            row["body"] = [_spec_string(one, f"a paragraph on screen {sid!r}", MAX_TEXT)
                           for one in body]
        elif kind == "list":
            row["items"] = _spec_items(screen.get("items"), sid)
        else:
            row["fields"], row["save_label"] = _spec_form(screen, sid)
        buttons, opened = _spec_buttons(screen, sid)
        if buttons:
            row["buttons"] = buttons
        targets.extend(opened)
        out.append(row)
    start = _spec_id(raw.get("start"), "the app's start")
    if start not in ids:
        raise BuildRefused(f"the app starts at {start!r}, and no screen has that id")
    for sid, target in targets:
        if target not in ids:
            raise BuildRefused(f"a button on screen {sid!r} opens {target!r}, and no screen "
                               "has that id")
    return {"name": name, "package_tail": tail, "bg": bg, "accent": accent, "start": start,
            "screens": out}


def native_package(spec: dict) -> str:
    """The package id for a validated spec. The spec supplies only the tail;
    the fixed prefix is what keeps two Jarvis-made apps, and a Jarvis-made app
    and a real vendor's, from colliding."""
    tail = str(spec.get("package_tail", ""))
    if not _PKG_TAIL.match(tail):
        raise BuildRefused(f"package_tail {tail[:40]!r} cannot become an Android package name")
    return "com.jarvis.made." + tail


def spec_path(tdir: Path, *, shipped: bool = False) -> Path:
    """Where the spec is: the model's own `app.json` at the root of the task's
    copy (before the project is written), or the copy inside `assets/` that the
    APK will actually read (after it is)."""
    return Path(tdir) / (SPEC_ASSET if shipped else SPEC_FILE)


def read_spec(tdir: Path, *, shipped: bool = False) -> tuple:
    """(validated spec, the canonical JSON text that is written) or a refusal.

    The spec is READ AND CHECKED here, before the template is written or a card
    raised: a task whose `app.json` cannot be built is refused in plain words,
    and no project is half-written around it."""
    path = spec_path(tdir, shipped=shipped)
    try:
        data = path.read_bytes()
    except OSError:
        raise BuildRefused("app.json is not there")
    if len(data) > MAX_SPEC_BYTES:
        raise BuildRefused(f"app.json is larger than {MAX_SPEC_BYTES // 1024} KB")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise BuildRefused("app.json must be UTF-8 text")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BuildRefused(f"app.json is not valid JSON: {exc.msg} (line {exc.lineno}, "
                           f"column {exc.colno})")
    except RecursionError:
        # A spec nested thousands of arrays deep can exhaust the parser before
        # any of the checks run. It is still the model's data, so it is still a
        # plain refusal rather than a 500.
        raise BuildRefused("app.json is nested too deeply to check")
    spec = validate_spec(raw)
    canonical = json.dumps(spec, indent=2, ensure_ascii=True) + "\n"
    if len(canonical.encode("utf-8")) > MAX_SPEC_BYTES:
        raise BuildRefused(f"app.json is larger than {MAX_SPEC_BYTES // 1024} KB once tidied")
    return spec, canonical


# --------------------------------------------------------------------------
#   The toolchain on this PC
# --------------------------------------------------------------------------

def _first_dir(*candidates) -> Optional[Path]:
    for c in candidates:
        if not c:
            continue
        p = Path(str(c))
        if p.is_dir():
            return p
    return None


def _glob_dir(pattern: str) -> Optional[Path]:
    import glob
    hits = sorted(glob.glob(pattern))
    return Path(hits[-1]) if hits else None


def sdk_root() -> Optional[Path]:
    """The Android SDK folder, or None. `ANDROID_HOME` / `ANDROID_SDK_ROOT`
    first, then the place the Android installer puts it on Windows."""
    local = os.environ.get("LOCALAPPDATA") or ""
    return _first_dir(os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
                      (Path(local) / "Android" / "Sdk") if local else None)


def java_home() -> Optional[Path]:
    """The JDK folder, or None. A JDK 17 or newer is what the Android Gradle
    plugin needs; `JAVA_HOME` first, then the two places Windows installers
    use. The version is not compared here - Gradle says so itself, in words,
    in the build's own log."""
    return _first_dir(os.environ.get("JAVA_HOME"),
                      _glob_dir(r"C:\Program Files\Microsoft\jdk-1[7-9]*"),
                      _glob_dir(r"C:\Program Files\Eclipse Adoptium\jdk-1[7-9]*"),
                      _glob_dir(r"C:\Program Files\Java\jdk-1[7-9]*"))


def adb_path() -> Optional[Path]:
    """`adb` by full path. It is NOT on PATH on this PC (measured
    2026-10-30), so the SDK's `platform-tools` folder is looked in first."""
    sdk = sdk_root()
    if sdk is not None:
        exe = sdk / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
        if exe.is_file():
            return exe
    found = shutil.which("adb")
    return Path(found) if found else None


def wrapper_files() -> tuple:
    """The two Gradle wrapper files Jarvis carries, beside this module.

    They are Gradle's own files, copied BYTE for BYTE (Apache-2.0, credited in
    THIRD-PARTY-NOTICES.txt): the `gradlew.bat` that starts a build and the
    `gradle-wrapper.jar` it needs. Shipping them is what makes a build
    possible on a PC with no Gradle installed - which is this one, measured
    2026-10-30. `backend/test_android_builder.py` proves both are identical
    to `jarvis-client`'s copies."""
    here = Path(__file__).resolve().parent
    return (here / "jarvis-android-gradlew.bat", here / "jarvis-android-wrapper.jar")


def toolchain() -> dict:
    """What this PC has, in plain words, for the card and for the refusal."""
    sdk, java, adb = sdk_root(), java_home(), adb_path()
    missing = []
    if sdk is None:
        missing.append("the Android SDK (set ANDROID_HOME, or install it from "
                       "https://developer.android.com/studio)")
    if java is None:
        missing.append("a Java 17 JDK (set JAVA_HOME)")
    bat, jar = wrapper_files()
    if not bat.is_file() or not jar.is_file():
        missing.append("the Gradle wrapper files beside jarvis_hud.py "
                       "(jarvis-android-gradlew.bat, jarvis-android-wrapper.jar) - "
                       "run apply-patches.ps1 again")
    return {"sdk": str(sdk) if sdk else "", "java": str(java) if java else "",
            "adb": str(adb) if adb else "", "missing": missing,
            "ready": not missing}


# --------------------------------------------------------------------------
#   The project in a task's copy
# --------------------------------------------------------------------------

def _texts(name: str, title: str, background: str, accent: str, *, package: str = "",
           native: bool = False, spec_text: str = "") -> dict:
    """Every text file the template writes, by path inside the task's copy.

    `native` picks the second kind: the fixed screens activity and the
    validated spec in `assets/app.json`, instead of the owner's web page. The
    Gradle files, the permission-free manifest and the theme are the SAME
    strings for both kinds - one toolchain and one permission story.
    """
    pkg = package or package_name(name)
    texts = {
        "settings.gradle.kts": _fill(_SETTINGS_GRADLE, title=_xml(title)),
        "build.gradle.kts": _fill(_BUILD_GRADLE, agp=AGP_VERSION),
        "gradle.properties": _GRADLE_PROPERTIES,
        "gradle/wrapper/gradle-wrapper.properties": _WRAPPER_PROPERTIES,
        "app/build.gradle.kts": _fill(_APP_BUILD_GRADLE, package=pkg,
                                      compile_sdk=COMPILE_SDK, min_sdk=MIN_SDK,
                                      target_sdk=TARGET_SDK),
        "app/src/main/AndroidManifest.xml": _MANIFEST,
        "app/src/main/java/" + pkg.replace(".", "/") + "/MainActivity.kt":
            _fill(_MAIN_ACTIVITY_SCREENS if native else _MAIN_ACTIVITY, package=pkg),
        "app/src/main/res/values/strings.xml":
            '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
            f'    <string name="app_name">{_xml(title)}</string>\n</resources>\n',
        "app/src/main/res/values/colors.xml":
            '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
            f'    <color name="jarvis_background">{background}</color>\n'
            f'    <color name="jarvis_accent">{accent}</color>\n</resources>\n',
        "app/src/main/res/values/themes.xml": _THEMES,
    }
    if native:
        texts[SPEC_ASSET] = spec_text
    return texts


def template_paths(name: str, *, package: str = "", native: bool = False) -> list:
    """Every path (relative, forward slashes) the template writes: the fixed
    project first, then the three web files - or, for the native-screens kind,
    the one spec in `assets/`. What the API shows and what a test checks, so
    nothing in the project is a surprise."""
    paths = sorted(_texts(name, "App", "#101828", "#7cc4ff", package=package, native=native))
    if not native:
        paths += [f"{ASSET_DIR}/{a}" for a in ASSETS]
    return paths + ["gradlew.bat", "gradle/wrapper/gradle-wrapper.jar"]


def is_template(tdir: Path) -> bool:
    """Is this task's copy already a Jarvis Android project?"""
    return (Path(tdir) / "settings.gradle.kts").is_file() and \
        (Path(tdir) / "app" / "build.gradle.kts").is_file()


def task_kind(tdir: Path) -> str:
    """Which kind of Android project this TASK asks for.

    The task's own files are the choice, so the two cannot drift: a task that
    carries `app.json` (the model's spec) is native screens, and a task
    without one is the WebView app. No separate flag exists to fall out of
    step with what will really be built."""
    return NATIVE if spec_path(tdir).is_file() else WEBVIEW


def project_kind(tdir: Path) -> str:
    """Which kind a WRITTEN project is, from what it carries: "native" when
    its assets hold the spec the activity reads, "webview" when they hold the
    page - and "" when this is not a Jarvis Android project at all."""
    tdir = Path(tdir)
    if not is_template(tdir):
        return ""
    return NATIVE if (tdir / SPEC_ASSET).is_file() else WEBVIEW


def native_facts(tdir: Path) -> tuple:
    """(the app's name, screen count) when this task carries a native-screens
    spec, or ("", 0) when it does not or the spec cannot be read.

    For the status read only, so a half-written task still answers instead of
    raising. The build card checks the spec properly and refuses."""
    if (project_kind(tdir) or task_kind(tdir)) != NATIVE:
        return "", 0
    try:
        spec, _text = read_spec(tdir, shipped=bool(project_kind(tdir)))
    except BuildRefused:
        return "", 0
    return str(spec["name"]), len(spec["screens"])


@dataclass
class TemplatePlan:
    """What writing the template will do, decided before anything is written."""
    project: str
    task: str
    tdir: Path
    kind: str = WEBVIEW
    title: str = ""
    background: str = "#101828"
    accent: str = "#7cc4ff"
    package: str = ""
    assets: dict = field(default_factory=dict)
    #: The validated native-screens spec, and the exact JSON text written into
    #: `assets/app.json`. Empty for the WebView kind.
    spec: dict = field(default_factory=dict)
    spec_text: str = ""
    screens: int = 0
    files: list = field(default_factory=list)
    refused: str = ""

    def detail(self) -> dict:
        """What the gate records - no file contents."""
        files = self.files or template_paths(self.project, package=self.package,
                                             native=self.kind == NATIVE)
        return {"project": self.project, "files": len(files), "kind": self.kind,
                "screens": self.screens}


def plan_template(name: str, task: str, *, title: str = "", background: str = "",
                  accent: str = "", assets: Optional[dict] = None) -> TemplatePlan:
    """Every check the template write needs, done BEFORE a byte is written.

    The task's own files choose the kind. For the WebView kind the checks are:
    the app is an Android app, the task's copy exists and has no project yet,
    the title and both colours are valid, and every asset is one of the three
    names on the closed list, text, and small enough. For the native-screens
    kind the whole `app.json` is validated here instead, and a title, colour or
    page passed beside it is refused rather than allowed to become a second
    source of truth."""
    plan = TemplatePlan(project=name, task=task, tdir=W.task_dir(name, task))
    meta = W.app_meta(name)
    if meta["kind"] != KIND:
        plan.refused = NOT_ANDROID
        return plan
    if not plan.tdir.is_dir():
        plan.refused = "that task is gone - it was merged or thrown away"
        return plan
    if is_template(plan.tdir):
        plan.refused = "this task already has an Android project - start a new task to " \
                       "change it"
        return plan
    # The two Gradle wrapper files are checked HERE, with everything else, so a
    # missing one refuses before a single byte of a half-project is written.
    bat, jar = wrapper_files()
    if not bat.is_file() or not jar.is_file():
        plan.refused = "the Gradle wrapper files are missing from the backend folder " \
                       "(jarvis-android-gradlew.bat, jarvis-android-wrapper.jar) - run " \
                       "apply-patches.ps1 again"
        return plan
    plan.kind = task_kind(plan.tdir)
    if plan.kind == NATIVE:
        if assets:
            plan.refused = ("this task's app.json makes it a native-screens app, so there "
                            "is no web page to pass")
            return plan
        for what, value in (("a title", title), ("a background colour", background),
                            ("an accent colour", accent)):
            if value:
                plan.refused = (f"this task's app.json makes it a native-screens app, so "
                                f"{what} comes from app.json, not from the request")
                return plan
        try:
            plan.spec, plan.spec_text = read_spec(plan.tdir)
            plan.title = plan.spec["name"]
            plan.background = plan.spec["bg"]
            plan.accent = plan.spec["accent"]
            plan.package = native_package(plan.spec)
            plan.screens = len(plan.spec["screens"])
        except BuildRefused as exc:
            plan.refused = str(exc)
            return plan
        plan.files = template_paths(plan.project, package=plan.package, native=True)
        return plan
    try:
        plan.title = check_title(title or meta["title"] or name)
        plan.background = check_colour(background or "#101828", "the background colour")
        plan.accent = check_colour(accent or "#7cc4ff", "the accent colour")
    except BuildRefused as exc:
        plan.refused = str(exc)
        return plan
    plan.package = package_name(name)
    given = assets or {}
    if not isinstance(given, dict):
        plan.refused = "the page must be given as a set of files"
        return plan
    for key in given:
        if key not in ASSETS:
            plan.refused = (f"{str(key)[:40]!r} is not one of this project's files - only "
                            f"{', '.join(ASSETS)} are written")
            return plan
    for key, content in given.items():
        if not isinstance(content, str):
            plan.refused = f"{key} must be text"
            return plan
        if len(content.encode("utf-8")) > MAX_ASSET_BYTES:
            plan.refused = f"{key} is larger than {MAX_ASSET_BYTES // 1024} KB"
            return plan
        plan.assets[key] = content
    plan.files = template_paths(name)
    return plan


def write_template(plan: TemplatePlan) -> dict:
    """Writes the fixed project and either the page or the validated screens
    into the task's copy.

    No card (APP-BUILDER-DESIGN.md): these files land only in the task's own
    copy and nothing runs them. Every path is a constant of this module or one
    of the closed lists (three web names, or the one spec) - the caller never
    supplies a path. For the native-screens kind the bytes written into
    `assets/app.json` are the VALIDATED ones, not the model's original text:
    what the phone reads is exactly what was checked."""
    if plan.refused:
        raise BuildRefused(plan.refused)
    tdir = plan.tdir
    if not tdir.is_dir():
        raise BuildRefused("that task is gone - it was merged or thrown away")
    if is_template(tdir):
        raise BuildRefused("this task already has an Android project")
    if plan.kind == NATIVE:
        if not plan.spec_text:
            raise BuildRefused("this task's app.json has not been read yet")
        texts = _texts(plan.project, plan.title, plan.background, plan.accent,
                       package=plan.package, native=True, spec_text=plan.spec_text)
    else:
        texts = _texts(plan.project, plan.title, plan.background, plan.accent,
                       package=plan.package)
        texts[f"{ASSET_DIR}/index.html"] = plan.assets.get("index.html") or \
            _fill(_DEFAULT_INDEX, title=_xml(plan.title))
        texts[f"{ASSET_DIR}/app.css"] = plan.assets.get("app.css") or \
            _fill(_DEFAULT_CSS, background=plan.background, accent=plan.accent)
        texts[f"{ASSET_DIR}/app.js"] = plan.assets.get("app.js") or \
            _fill(_DEFAULT_JS, title=plan.title.replace("'", ""))
    bat, jar = wrapper_files()
    with W._LOCK:
        for rel, text in texts.items():
            target = W.safe_path(tdir, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode("utf-8"))
        # The two wrapper files are GRADLE's, so they are copied as bytes,
        # never re-written: a text round-trip would corrupt the jar.
        #
        # ONE conversion, and it is the reason this file ships as LF: this
        # repository stores every text file with LF endings (.gitattributes),
        # so the copy beside this module is LF - but a Windows batch file needs
        # CRLF, because cmd.exe mis-reads labels in an LF-only file, and
        # `gradlew.bat` is nothing but labels and `goto`s. So the CRLF the file
        # needs is put back HERE, where the project is written, and the
        # generated copy is byte for byte Gradle's own with Windows endings
        # (backend/test_android_builder.py checks both halves).
        for src, rel in ((bat, "gradlew.bat"), (jar, "gradle/wrapper/gradle-wrapper.jar")):
            if not src.is_file():
                raise BuildRefused(f"{src.name} is missing from the backend folder - run "
                                   "apply-patches.ps1 again")
            target = W.safe_path(tdir, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            data = src.read_bytes()
            if rel.endswith(".bat"):
                data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            target.write_bytes(data)
    _audit("android.template", {"files": len(texts) + 2})
    return {"ok": True, "files": len(texts) + 2,
            "package": plan.package or package_name(plan.project),
            "title": plan.title, "kind": plan.kind, "screens": plan.screens}


# --------------------------------------------------------------------------
#   The build: `gradlew.bat assembleDebug`, exactly
# --------------------------------------------------------------------------

@dataclass
class CommandPlan:
    """One command, decided and shown before it is run."""
    kind: str
    project: str
    task: str
    tdir: Path
    argv: list
    cwd: Path
    seconds: float
    apk: Optional[Path] = None
    refused: str = ""
    #: What the card carries, in words, and never a file's contents.
    says: str = ""
    #: Which kind of Android app this is ("webview" or "native"), the name the
    #: phone will show, and how many screens a native one has. Read from the
    #: written project, so the card names what will really be built.
    app_kind: str = WEBVIEW
    title: str = ""
    screens: int = 0

    def detail(self) -> dict:
        return {"project": self.project, "task": self.task,
                "command": _shown(self.argv), "cwd": str(self.cwd),
                "app_kind": self.app_kind, "screens": self.screens}


def _shown(argv) -> str:
    """A command as one line, for a card. A space in a path is quoted so the
    line can be pasted into a terminal and mean the same thing."""
    out = []
    for a in argv:
        s = str(a)
        out.append(f'"{s}"' if " " in s else s)
    return " ".join(out)


def build_command(tdir: Path) -> list:
    """THE build command. One function, one place, so a test can pin it."""
    exe = Path(tdir) / ("gradlew.bat" if WINDOWS else "gradlew")
    return [str(exe), GRADLE_TASK]


def _screens_words(count: int) -> str:
    return f"{count} screen" if count == 1 else f"{count} screens"


def plan_build(name: str, task: str) -> CommandPlan:
    plan = CommandPlan(kind="build", project=name, task=task,
                       tdir=W.task_dir(name, task), argv=[], cwd=W.task_dir(name, task),
                       seconds=BUILD_SECONDS)
    if W.app_meta(name)["kind"] != KIND:
        plan.refused = NOT_ANDROID
        return plan
    if not plan.tdir.is_dir():
        plan.refused = "that task is gone - it was merged or thrown away"
        return plan
    if not is_template(plan.tdir):
        plan.refused = NOT_TEMPLATE
        return plan
    if not WINDOWS:
        plan.refused = "Jarvis builds Android apps on Windows only, where the Android SDK " \
                       "and the phone's cable are"
        return plan
    have = toolchain()
    if not have["ready"]:
        plan.refused = "this PC is missing " + ", ".join(have["missing"])
        return plan
    plan.app_kind = project_kind(plan.tdir)
    plan.title = name
    if plan.app_kind == NATIVE:
        # The spec is checked AGAIN here, from the copy the APK will read, and
        # before a card is raised: a project whose spec was changed by hand (or
        # half-written) is refused in plain words rather than built.
        try:
            spec, _text = read_spec(plan.tdir, shipped=True)
        except BuildRefused as exc:
            plan.refused = str(exc)
            return plan
        plan.title = spec["name"]
        plan.screens = len(spec["screens"])
    plan.argv = build_command(plan.tdir)
    plan.apk = plan.tdir / APK_REL
    if plan.app_kind == NATIVE:
        first = (f'Build the Android app "{plan.title}" - native screens: '
                 f"{_screens_words(plan.screens)}, drawn by the app itself with ordinary "
                 "Android views and not a web page, in this task's copy:\n")
    else:
        first = f'Build the Android app "{name}" in this task\'s copy:\n'
    plan.says = first + (
        f"  command: {_shown(plan.argv)}\n"
        f"  folder:  {plan.tdir}\n"
        f"  Android SDK: {have['sdk']}\n"
        f"  Java:        {have['java']}\n\n"
        "This runs Gradle, which runs other people's build code with your own Windows "
        "permissions, so it asks every time. The FIRST build on this PC downloads the "
        "Gradle distribution (about 130 MB) and the Android Gradle plugin from "
        "services.gradle.org, dl.google.com and repo.maven.apache.org - that is a "
        "download, so nothing of yours is sent anywhere. Later builds reuse what is "
        "already in your Gradle folder.\n\n"
        f"The app it makes is at: {APK_REL}\n"
        "Nothing is installed on your phone by this card - that is a second card."
    )
    return plan


def build_env(have: Optional[dict] = None) -> dict:
    """The environment the build runs with: the allowlist every child program
    gets (`jarvis_child_env`), plus the three PATHS the toolchain needs. No
    token, no key, no password: `inherited()` drops anything that looks like
    one, and a test proves it."""
    import jarvis_child_env
    have = have or toolchain()
    env = jarvis_child_env.inherited()
    if have.get("sdk"):
        env["ANDROID_HOME"] = have["sdk"]
        env["ANDROID_SDK_ROOT"] = have["sdk"]
    if have.get("java"):
        env["JAVA_HOME"] = have["java"]
    # Gradle's own folder is left at its default (GRADLE_USER_HOME if the owner
    # set it, else ~/.gradle), so a build reuses what this PC already has.
    # Gradle runs single-use: no daemon outlives the card.
    env["GRADLE_OPTS"] = "-Dorg.gradle.daemon=false"
    return env


def _tail(path: Path, limit: int = MAX_LOG_CHARS) -> str:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return ""
    text = data.decode("utf-8", "replace")
    return text[-limit:]


def _run(argv: list, cwd: Path, env: dict, seconds: float, log: Path) -> tuple:
    """Runs one command with its output going to a FILE, never into memory:
    a build can print megabytes, and a cap applied after reading them all is
    not a cap. Returns (returncode, log path). -1 means the time limit was
    hit; -2 means it would not start."""
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(log, "wb") as fh:
            try:
                done = subprocess.run(argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                                      stdout=fh, stderr=subprocess.STDOUT, timeout=seconds)
            except subprocess.TimeoutExpired:
                return -1, log
            except (OSError, ValueError):
                return -2, log
    except OSError:
        return -2, log
    return done.returncode, log


def run_build(plan: CommandPlan, approved: bool = False) -> dict:
    """Runs exactly `plan.argv` in exactly `plan.cwd`. Refuses without a yes,
    and refuses to run anything but the one documented command."""
    if not approved:
        return {"ok": False, "error": "not approved", "why": "not_approved"}
    if plan.refused:
        return {"ok": False, "error": plan.refused, "why": "plan_refused"}
    if plan.argv != build_command(plan.tdir):
        return {"ok": False, "error": "that is not the build command", "why": "wrong_build"}
    log = plan.tdir / BUILD_LOG_REL
    with _S_ONE:
        code, log = _run(plan.argv, plan.cwd, build_env(), plan.seconds, log)
    tail = _tail(log)
    apk = plan.tdir / APK_REL
    if code == -1:
        return {"ok": False, "why": "timed_out", "log": tail,
                "error": f"the build took longer than {int(plan.seconds / 60)} minutes and "
                         "was stopped"}
    if code == -2:
        return {"ok": False, "why": "would_not_start", "log": tail,
                "error": "the build would not start - is gradlew.bat still in the task's "
                         "copy?"}
    if code != 0 or not apk.is_file():
        _audit("android.build", {"ok": False})
        return {"ok": False, "why": "build_failed", "log": tail,
                "error": f"the build failed (exit code {code}). The end of what Gradle "
                         "said is on the card."}
    _audit("android.build", {"ok": True})
    return {"ok": True, "apk": str(apk), "bytes": apk.stat().st_size, "log": tail}


# --------------------------------------------------------------------------
#   The install: `adb install -r <the apk>`, exactly
# --------------------------------------------------------------------------

def install_command(adb: Path, apk: Path) -> list:
    """THE install command. One function, one place, so a test can pin it:
    adb by full path, `install`, `-r`, and the APK. Nothing else, ever."""
    return [str(adb), "install", "-r", str(apk)]


def apk_inside(tdir: Path) -> Optional[Path]:
    """The APK this build made, if it is really inside the task's copy."""
    try:
        target = (Path(tdir) / APK_REL)
        real_root = os.path.realpath(tdir)
        real = os.path.realpath(target)
        if os.path.commonpath([real_root, real]) != real_root:
            return None
    except (OSError, ValueError):
        return None
    if not target.is_file() or target.suffix.lower() != ".apk":
        return None
    if target.stat().st_size <= 0:
        return None
    return target


def plan_install(name: str, task: str) -> CommandPlan:
    plan = CommandPlan(kind="install", project=name, task=task,
                       tdir=W.task_dir(name, task), argv=[], cwd=W.task_dir(name, task),
                       seconds=INSTALL_SECONDS)
    if W.app_meta(name)["kind"] != KIND:
        plan.refused = NOT_ANDROID
        return plan
    if not plan.tdir.is_dir():
        plan.refused = "that task is gone - it was merged or thrown away"
        return plan
    apk = apk_inside(plan.tdir)
    if apk is None:
        plan.refused = BUILD_FIRST
        return plan
    adb = adb_path()
    if adb is None:
        plan.refused = ("adb was not found - it is in the Android SDK's platform-tools "
                        "folder, which this PC does not have")
        return plan
    plan.apk = apk
    plan.argv = install_command(adb, apk)
    plan.app_kind = project_kind(plan.tdir)
    plan.title = name
    if plan.app_kind == NATIVE:
        # Name the app the phone will actually show. A spec that cannot be read
        # is not a reason to refuse the INSTALL of an APK that already exists -
        # the build card is where the spec is checked - so fall back to the
        # folder's name rather than inventing a failure.
        try:
            spec, _text = read_spec(plan.tdir, shipped=True)
            plan.title = spec["name"]
        except BuildRefused:
            plan.title = name
    plan.says = (
        f"Put the app \"{plan.title}\" on your phone:\n"
        f"  command: {_shown(plan.argv)}\n"
        f"  file:    {apk}  ({apk.stat().st_size // 1024} KB)\n\n"
        "This is a SIDELOAD: it replaces the copy already installed, if any, and it never "
        "goes near the Play Store. It needs the phone on this PC's cable with USB "
        "debugging allowed. Jarvis runs no other adb command, so it cannot read anything "
        "on your phone or uninstall anything.\n\n"
        "If the phone says the app could not be installed, the build is probably signed "
        "for a different copy already on it - uninstall that copy yourself and ask again."
    )
    return plan


def run_install(plan: CommandPlan, approved: bool = False) -> dict:
    """Runs exactly `adb install -r <apk>`. Refuses without a yes, refuses an
    APK that is not inside the task's copy, and refuses any other argument."""
    if not approved:
        return {"ok": False, "error": "not approved", "why": "not_approved"}
    if plan.refused:
        return {"ok": False, "error": plan.refused, "why": "plan_refused"}
    apk = apk_inside(plan.tdir)
    adb = adb_path()
    if apk is None or adb is None or plan.argv != install_command(adb, apk):
        return {"ok": False, "error": "that is not the install command", "why": "wrong_install"}
    log = plan.tdir / "build" / "jarvis-install.log"
    with _S_ONE:
        code, log = _run(plan.argv, plan.cwd, build_env(), plan.seconds, log)
    tail = _tail(log)
    if code == -1:
        return {"ok": False, "why": "timed_out", "log": tail,
                "error": "installing took too long and was stopped"}
    if code != 0:
        _audit("android.install", {"ok": False})
        return {"ok": False, "why": "install_failed", "log": tail,
                "error": f"the phone did not take the app (exit code {code}). Is it on the "
                         "cable with USB debugging allowed? The end of what adb said is on "
                         "the card."}
    _audit("android.install", {"ok": True})
    return {"ok": True, "log": tail}


# --------------------------------------------------------------------------
#   The cards
# --------------------------------------------------------------------------

def _audit(event: str, detail: dict) -> None:
    P._audit(event, detail)


def _key(app: str, task: str) -> str:
    return f"{app}/{task}"


def _waiting(app: str, task: str) -> Optional[str]:
    with _S_LOCK:
        p = _S_STATE["pending"].get(_key(app, task))
        return p["kind"] if p else None


def _last(app: str, task: str) -> Optional[dict]:
    with _S_LOCK:
        last = _S_STATE["last"].get(_key(app, task))
        return dict(last) if last else None


def withdraw(app: str, task: str) -> None:
    """A card waiting for this task is withdrawn: its yes will do nothing.
    Called when the task is thrown away or merged."""
    with _S_LOCK:
        p = _S_STATE["pending"].pop(_key(app, task), None)
        if p:
            _S_STATE["withdrawn"].add(p["token"])
            _S_STATE["silent"].add(p["token"])
        _S_STATE["last"].pop(_key(app, task), None)


def _finish(app: str, task: str, token: str, outcome: str, why: str = "") -> None:
    message = OUTCOME_WORDS.get(outcome, "")
    if outcome == "refused" and why:
        message = f"{message} {_sentence(why)}"
    with _S_LOCK:
        p = _S_STATE["pending"].get(_key(app, task))
        if p and p.get("token") == token:
            _S_STATE["pending"].pop(_key(app, task), None)
        _S_STATE["withdrawn"].discard(token)
        if token in _S_STATE["silent"]:
            _S_STATE["silent"].discard(token)
            return
        _S_STATE["last"][_key(app, task)] = {
            "kind": p["kind"] if p else "", "outcome": outcome, "message": message,
            "at": time.time()}
    _audit(f"android.{outcome}", {})


def _sentence(text) -> str:
    s = str(text or "").strip() or "Something went wrong"
    s = s[:1].upper() + s[1:]
    return s if s.endswith((".", "?", "!", ">")) else s + "."


def _decide(plan: CommandPlan, token: str, action: str, gate: Callable,
            tier_of: Callable) -> None:
    text = plan.says
    detail = plan.detail()
    what = ("build one Android app with Gradle" if plan.kind == "build"
            else "put a built Android app on your phone")
    if plan.app_kind == NATIVE:
        what += " (native screens)"
    detail.update(what=what, leaves_this_pc=False)
    app, task = plan.project, plan.task
    try:
        v = gate(action, detail, text)
    except Exception as exc:
        return _finish(app, task, token, "refused",
                       f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(action) != "ask":
        return _finish(app, task, token, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person "
                       f"saying yes")
    if not P._person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _finish(app, task, token, outcome)
        return _finish(app, task, token, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _S_ONE:
        # The withdrawn check is READ inside the lock and ACTED ON outside it:
        # _finish() takes the same lock, and calling it from inside that block
        # deadlocked the whole card (found 2026-10-30 by a test that throws the
        # task away while its card is up, and the two processes sat at zero CPU
        # for ever). `_S_LOCK` is an RLock as well, so a future nested caller
        # cannot repeat it.
        with _S_LOCK:
            withdrawn = token in _S_STATE["withdrawn"]
        if withdrawn:
            return _finish(app, task, token, "withdrawn")
        try:
            r = (run_build(plan, approved=True) if plan.kind == "build"
                 else run_install(plan, approved=True))
        except Exception as exc:
            return _finish(app, task, token, "failed", type(exc).__name__)
    why = r.get("why", "")
    if r.get("ok"):
        return _finish(app, task, token, "built" if plan.kind == "build" else "installed")
    if why == "timed_out":
        return _finish(app, task, token, "timed_out")
    if why == "refused":
        return _finish(app, task, token, "refused", str(r.get("error", ""))[:400])
    _finish(app, task, token, "failed", str(r.get("error", ""))[:400])
    # Keep the end of the build's own words where the next GET can show them.
    with _S_LOCK:
        last = _S_STATE["last"].get(_key(app, task))
        if last:
            last["log"] = str(r.get("log", ""))[-4000:]


def _card_plumbing() -> dict:
    """The three callables a card needs, built here because a drop-in module
    gets only origin_ok/token_ok/read_body from the loader.

    `gate(action, detail, text)` blocks in the caller's thread until the owner
    answers and returns whether it was a yes; `tier_of(action)` reads the same
    policy table the core reads; `spawn(fn)` runs the wait in the background so
    the HTTP request returns 202 at once (the card, not the build, is what the
    route waits on). jarvis_gate.check() is the one entry point every other card
    goes through, so the Windows-Hello rules, the risk words and the audit row
    all still apply.
    """

    def gate(action: str, detail=None, text: str = ""):
        # Hand back the gate's Verdict itself, never a bool: _decide() reads
        # .tier, .outcome and P._person_said_yes() off it. Returning a bool made
        # the module refuse EVERY approved card with "the gate answered at tier
        # 'unknown'" (found on the owner's PC, 2026-10-30: the card was approved
        # on the desktop and the build still refused).
        import jarvis_gate
        return jarvis_gate.check(action, detail=detail if isinstance(detail, dict) else {},
                                 prompt=str(text or ""))

    def tier_of(action: str) -> str:
        try:
            import jarvis_gate
            return str(jarvis_gate._tiers().get(action, "unknown"))
        except Exception:
            return "unknown"

    def spawn(fn) -> None:
        threading.Thread(target=fn, name="jarvis-android-card", daemon=True).start()

    return {"gate": gate, "tier_of": tier_of, "spawn": spawn}


def _approval_doorbell() -> None:
    """Tell both apps the queue changed; they re-read /api/pending on this
    event. Silent on failure: the card is already up either way, and a missing
    doorbell only means the screens learn on their next read."""
    try:
        import jarvis_events
        import jarvis_gate
        jarvis_events.BUS.publish("approval", {"count": len(jarvis_gate.pending())})
    except Exception:
        pass


def _raise(app: str, task: str, plan: CommandPlan, action: str, *, gate: Callable,
           tier_of: Callable, spawn: Callable) -> tuple:
    if plan.refused:
        return 400, {"ok": False, "error": _sentence(plan.refused)}
    t = tier_of(action)
    if t != "ask":
        return 503, {"ok": False,
                     "error": f"{action} is tier {t!r} in jarvis-framework.toml; this needs "
                              "a person to say yes, so it must be 'ask'"}
    k = _key(app, task)
    with _S_LOCK:
        if k in _S_STATE["pending"]:
            return 409, {"ok": False, "error": CARD_WAITING}
        token = uuid.uuid4().hex
        _S_STATE["pending"][k] = {"token": token, "kind": plan.kind, "since": time.time()}
    try:
        spawn(lambda: _decide(plan, token, action, gate, tier_of))
    except Exception:
        with _S_LOCK:
            _S_STATE["pending"].pop(k, None)
        return 503, {"ok": False, "error": "Could not raise the approval card."}
    return 202, {"ok": True, "waiting": True, "card": action, "command": _shown(plan.argv),
                 "message": "Waiting for your approval. Nothing runs unless you say yes."}


# --------------------------------------------------------------------------
#   Routes
# --------------------------------------------------------------------------

PATH = "/api/projects"


def parse_route(route: str) -> Optional[tuple]:
    """None, or a tuple naming the route:
        ("status", pid, task)               /api/projects/<pid>/app/tasks/<t>/android
        ("template", pid, task)             .../android/template
        ("build", pid, task)                .../android/build
        ("install", pid, task)              .../android/install
    """
    if not isinstance(route, str) or not route.startswith(PATH + "/"):
        return None
    p = route[len(PATH) + 1:].split("/")
    if len(p) < 5 or not p[0] or p[1] != "app" or p[2] != "tasks" or not p[3]:
        return None
    if p[4] != "android":
        return None
    if len(p) == 5:
        return ("status", p[0], p[3])
    if len(p) == 6 and p[5] in ("template", "build", "install"):
        return (p[5], p[0], p[3])
    return None


def _resolve(store, pid: str):
    try:
        info = store.app_of(pid)
    except KeyError:
        return 404, {"ok": False, "error": "No such project."}
    if not info["app"]:
        return 404, {"ok": False, "error": "This project is not an app."}
    return info["app"], info["name"]


def status(app: str, task: str) -> dict:
    """What this task's Android project is, and what the next card would run.
    No secrets, no file contents: paths, counts and the toolchain."""
    tdir = W.task_dir(app, task)
    have = toolchain()
    build = plan_build(app, task)
    install = plan_install(app, task)
    apk = apk_inside(tdir)
    title, screens = native_facts(tdir)
    return {"ok": True, "app": app, "task": task, "template": is_template(tdir),
            "kind": project_kind(tdir) or task_kind(tdir), "title": title,
            "screens": screens,
            "toolchain": {"sdk": have["sdk"], "java": have["java"], "adb": have["adb"],
                          "missing": have["missing"]},
            "build": {"ready": not build.refused, "refused": _sentence(build.refused)
                      if build.refused else "", "command": _shown(build.argv)},
            "install": {"ready": not install.refused,
                        "refused": _sentence(install.refused) if install.refused else "",
                        "command": _shown(install.argv)},
            "apk": {"path": str(apk) if apk else "", "bytes": apk.stat().st_size
                    if apk else 0},
            "waiting": _waiting(app, task), "last": _last(app, task)}


def handle_get(route: str, query: str = "", *, store=None) -> tuple:
    store = store or P.get()
    hit = parse_route(route)
    if hit is None:
        return 404, {"ok": False, "error": "No such route."}
    if hit[0] != "status":
        return 405, {"ok": False, "error": "Use POST for this."}
    got = _resolve(store, hit[1])
    if isinstance(got[0], int):
        return got
    app = got[0]
    try:
        if not W.task_dir(app, hit[2]).is_dir():
            return 404, {"ok": False, "error": NO_TASK}
        return 200, status(app, hit[2])
    except W.WorkspaceError as exc:
        return 404, {"ok": False, "error": _sentence(exc)}


def handle_post(route: str, body, *, here: bool = False, store=None, **card) -> tuple:
    store = store or P.get()
    hit = parse_route(route)
    if hit is None:
        return 404, {"ok": False, "error": "No such route."}
    if hit[0] == "status":
        return 405, {"ok": False, "error": "Use GET for this."}
    if not here:
        # PC only, whatever else is wrong with the request: the SDK, the
        # Gradle build and the phone's cable are all on this machine.
        return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    got = _resolve(store, hit[1])
    if isinstance(got[0], int):
        return got
    app = got[0]
    task = hit[2]
    if not isinstance(body, dict):
        body = {}
    try:
        if not W.task_dir(app, task).is_dir():
            return 404, {"ok": False, "error": NO_TASK}
        if hit[0] == "template":
            plan = plan_template(app, task, title=body.get("title", ""),
                                 background=body.get("background", ""),
                                 accent=body.get("accent", ""),
                                 assets=body.get("assets"))
            if plan.refused:
                return 400, {"ok": False, "error": _sentence(plan.refused)}
            done = write_template(plan)
            return 200, {"ok": True, "template": done, "status": status(app, task)}
        if hit[0] == "build":
            return _raise(app, task, plan_build(app, task), BUILD_ACTION, **card)
        if hit[0] == "install":
            return _raise(app, task, plan_install(app, task), INSTALL_ACTION, **card)
    except W.WorkspaceError as exc:
        return 404, {"ok": False, "error": _sentence(exc)}
    except BuildRefused as exc:
        return 400, {"ok": False, "error": _sentence(exc)}
    except Exception as exc:
        return 503, {"ok": False, "error": type(exc).__name__}
    return 404, {"ok": False, "error": "No such route."}


_ARMED = False


def install(handler_cls, *, origin_ok, token_ok, read_body,
            gate: Optional[Callable] = None, tier_of: Optional[Callable] = None,
            spawn: Optional[Callable] = None) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so the Android routes are
    answered here, after the server's own origin and token checks. Every other
    request goes to the original. Returns the banner line.

    Installed by the drop-in loader (`plugins/ready/android-builder`), the same
    way every other module's routes are, so this feature adds no patch to
    `jarvis_hud.py`.

    `gate`/`tier_of`/`spawn` may be injected by a caller that already has them;
    when they are not (the drop-in loader hands over only the three core
    callbacks) this module builds them itself from jarvis_gate, jarvis_events
    and a daemon thread - see [_card_plumbing]. Without that default the build
    and install routes called `_raise()` with no plumbing, raised TypeError in
    the real process and answered 503 (found on the owner's PC, 2026-10-30)."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    built = _card_plumbing()
    card = {"gate": gate or built["gate"], "tier_of": tier_of or built["tier_of"],
            "spawn": spawn or built["spawn"]}
    if getattr(post0, "_jarvis_android", False):
        _ARMED = True
        return "  android    Made apps (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if parse_route(route) is None:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, parts.query)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if parse_route(route) is None:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"ok": False, "error": type(exc).__name__})
        try:
            code, out = handle_post(route, body, here=P._from_this_pc(*P._peer_local(self)),
                                    **card)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        if code == 202 and isinstance(out, dict) and out.get("waiting"):
            _approval_doorbell()
        return self._send(code, out)

    do_GET._jarvis_android = True
    do_POST._jarvis_android = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    return "  android    Made apps: template, build and install (one card each)"


def _reset_for_tests() -> None:
    global _ARMED
    with _S_LOCK:
        _S_STATE["pending"].clear()
        _S_STATE["withdrawn"].clear()
        _S_STATE["silent"].clear()
        _S_STATE["last"].clear()
    _ARMED = False
