#!/usr/bin/env python3
"""Android-builder honesty (2026-10-31).

Live Jarvis said it could not build Android apps because it has no tools to
write code or compile projects. False: backend/jarvis_android_builder.py builds
a fixed minimal WebView project in one project task (gradlew.bat assembleDebug
behind app_build_android) and installs the APK over the cable (adb install -r
behind app_install_android). This suite pins the fast-path answers to the
module's own constants and to a fake toolchain report.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import jarvis_quick as Q  # noqa: E402
import jarvis_android_builder as AB  # noqa: E402

PASSED, FAILED = [], []


class Stub:
    def mark_command(self, text):
        pass

    def note_set(self, *a, **k):
        pass

    def last_set(self, *a, **k):
        return None


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def ask(text):
    return Q.answer(text, sched=Stub(), now=1793505565.0, peer="127.0.0.1", local=True)


def test_source_truth():
    check("the module's card ids are the ones the answers name",
          AB.BUILD_ACTION == "app_build_android" and AB.INSTALL_ACTION == "app_install_android",
          f"{AB.BUILD_ACTION} / {AB.INSTALL_ACTION}")
    check("the build is exactly gradlew.bat assembleDebug",
          AB.build_command(Path("C:/x"))[-1] == "assembleDebug", str(AB.build_command(Path("C:/x"))))
    check("the install is exactly adb install -r",
          "-r" in AB.install_command(Path("adb.exe"), Path("app.apk")), "install command")
    check("the loader/manifest summary names both cards",
          "one approval card for the build" in (ROOT / "plugins/ready/android-builder/plugin.json").read_text(encoding="utf-8"))


def test_capability_and_needs():
    for text in ("can you build android apps?", "are you able to build android apps for me?",
                 "can you build me an app for my phone?"):
        r = ask(text)
        check(f"{text!r} is answered by the fast path",
              r is not None and r.intent == "android_capability", r.intent if r else "model")
        reply = r.reply if r else ""
        check("... it says Android can really be built", "Yes" in reply and "Android" in reply,
              reply[:220])
        check("... it does NOT repeat the old denial",
              "can't build android" not in reply.lower()
              and "no tools to write code" not in reply.lower(), reply[:220])
        check("... it names the two cards and the fixed template",
              "app_build_android" in reply and "app_install_android" in reply
              and "index.html" in reply, reply[:400])
    for text in ("what does the android builder need?",
                 "what do you need to build an android app?"):
        r = ask(text)
        check(f"{text!r} answers the requirements",
              r is not None and r.intent == "android_needs"
              and "Android SDK" in r.reply and "Java 17" in r.reply, r.reply if r else "model")
    r = ask("how do I ask you to build one?")
    check("'how do I ask you to build one?' is the Android how-to",
          r is not None and r.intent == "android_howto", r.intent if r else "model")
    r = ask("can you compile and install it?")
    check("compile+install names both cards",
          r is not None and r.intent == "android_build_install"
          and "app_build_android" in r.reply and "app_install_android" in r.reply,
          r.reply if r else "model")


def test_toolchain_state_is_real():
    Q._android_state = lambda: {"ready": True, "missing": [], "sdk": "C:/sdk", "java": "C:/jdk",
                                "adb": "C:/adb.exe"}
    try:
        r = ask("what does the android builder need?")
        check("a ready toolchain says this PC has it", r is not None and "ready" in r.reply.lower(),
              r.reply if r else "model")
        Q._android_state = lambda: {"ready": False, "sdk": "", "java": "",
                                    "adb": "", "missing": ["a Java 17 JDK (set JAVA_HOME)"]}
        r = ask("what does the android builder need?")
        check("a missing piece is named in plain words",
              r is not None and "missing" in r.reply.lower() and "Java 17" in r.reply,
              r.reply if r else "model")
    finally:
        Q._android_state = _ORIG_STATE


def test_over_capture():
    for text in ("can you build a website for me?", "build a React app",
                 "what does Android Studio need?", "can you fix my phone?",
                 "can you build a house?"):
        r = Q.match(text)
        check(f"not an Android-builder question: {text!r}",
              r is None or not str(r.name).startswith("android_"), r.name if r else "model")


def test_prompt_and_catalogue():
    mf = (ROOT / "backend" / "jarvis-primary.Modelfile").read_text(encoding="utf-8")
    m = re.search(r'SYSTEM """(.*?)"""', mf, re.S)
    text = m.group(1) if m else ""
    check("the Modelfile says Android can really be built",
          "build a small Android app" in text, "missing line")
    profiles = (ROOT / "backend" / "jarvis_profiles.py").read_text(encoding="utf-8")
    check("the tuned-model copy carries the same line", "build a small Android app" in profiles)
    line = next((ln for ln in text.splitlines() if "build a small Android app" in ln), "")
    check("the prompt line names the cards and the requirements",
          "app_build_android" in line and "app_install_android" in line and "Android SDK" in line,
          line)
    check("the prompt line carries no token or secret",
          not re.search(r"token|secret|api[ _-]?key|Bearer", line, re.I), line)
    rows = json.loads((ROOT / "features/features.json").read_text(encoding="utf-8"))
    row = next(r for r in rows if r["id"] == "android-builder")
    joined = " ".join(str(row.get(k) or "") for k in ("what", "where", "asks", "limit"))
    check("the catalogue row carries the fixed template and both cards",
          "fixed" in joined and "app_build_android" in joined and "app_install_android" in joined,
          joined[:300])
    check("... and the real requirements/limits",
          "Android SDK" in joined and "Java 17" in joined and "Play Store" in joined, joined[:300])


_ORIG_STATE = Q._android_state


def main():
    tests = [test_source_truth, test_capability_and_needs, test_toolchain_state_is_real,
             test_over_capture, test_prompt_and_catalogue]
    for t in tests:
        print("\n-- " + t.__name__ + " " + "-" * 50)
        try:
            t()
        except Exception as exc:            # noqa: BLE001
            check(t.__name__ + " ran", False, repr(exc))
    print("\n" + "=" * 74)
    print(f"PASS {len(PASSED)}  FAIL {len(FAILED)}  SKIP 0")
    for name in FAILED:
        print("  FAIL:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
